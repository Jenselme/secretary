#! /usr/bin/python
# -*- coding: utf-8 -*-


"""
Secretary
    This project is a document engine which make use of LibreOffice
    documents as templates and use the semantics of jinja2 to control
    variable printing and control flow.

    To render a template:
        engine = Renderer()
        result = engine.render(template_file, foo=bar, ...)


    Copyright (c) 2012-2015 By:
        * Christopher Ramirez <chris.ramirezg@gmail.com>
        * Andrés Reyes Monge (github.com/armonge)
        * Anton Kochnev (github.com/ak04nv)
        * DieterBuys (github.com/DieterBuys)

    Licensed under the MIT license.
"""

from __future__ import unicode_literals, print_function

import io
import re
import sys
import logging
import zipfile
from os import path
from mimetypes import guess_type, guess_extension
from uuid import uuid4
from jinja2 import Environment, Undefined

from filters import PadStringFilter, ImageFilter

from renders.odtrender import ODTRender

try:
    if sys.version_info.major == 3:
        xrange = range
        basestring = (str, bytes)
except AttributeError:
    # On Python 2.6 sys.version_info is a tuple
    if not isinstance(sys.version_info, tuple):
        raise


# ---- Exceptions
class SecretaryError(Exception):
    pass

class UndefinedSilently(Undefined):
    # Silently undefined,
    # see http://stackoverflow.com/questions/6182498
    def silently_undefined(*args, **kwargs):
        return ''

    return_new = lambda *args, **kwargs: UndefinedSilently()

    __unicode__ = silently_undefined
    __str__ = silently_undefined
    __call__ = return_new
    __getattr__ = return_new

class MediaInterface(object):
    """Provides media handling capabilities to Renderer class."""
    def __init__(self, **kwargs):
        self.media_path = kwargs.pop('media_path', '')
        self.media_callback = self.fs_loader

    def media_loader(self, callback):
        """This sets the the media loader. A user defined function which
        loads media. The function should take a template value, optionals
        args and kwargs. Is media exists should return a tuple whose first
        element if a file object type representing the media and its second
        elements is the media mimetype.

        See Renderer.fs_loader funcion for an example"""
        self.media_callback = callback
        return callback

    def fs_loader(self, media, *args, **kwargs):
        """Loads a file from the file system.
        :param media: A file object or a relative or absolute path of a file.
        :type media: unicode
        """
        if hasattr(media, 'seek') and hasattr(media, 'read'):
            return (media, 'image/jpeg')
        elif path.isfile(media):
            filename = media
        else:
            if not self.media_path:
                self.log.debug('media_path property not specified to load images from.')
                return

            filename = path.join(self.media_path, media)
            if not path.isfile(filename):
                self.log.debug('Media file "%s" does not exists.' % filename)
                return

        mime = guess_type(filename)
        return (open(filename, 'rb'), mime[0] if mime else None)


class RendererFilterInterface(object):
    """Provies an interface for attaching filters to Renderer environment and jobs."""
    filters = {}
    on_job_starts_callbacks = []
    on_job_ends_callbacks = []
    before_xml_render_callbacks = []
    after_xml_render_callbacks = []

    def register_filter(self, filtername, filter):
        implementation = filter
        if hasattr(filter, 'render') and hasattr(filter.render, '__call__'):
            self.filters[filtername] = filter
            implementation = filter.render

        self.environment.filters[filtername] = implementation

    def register_for_job_start(self, callback):
        self.on_job_starts_callbacks.append(callback)

    def register_for_job_end(self, callback):
        self.on_job_ends_callbacks.append(callback)

    def register_before_xml_render(self, callback):
        self.before_xml_render_callbacks.append(callback)

    def register_after_xml_render(self, callback):
        self.after_xml_render_callbacks.append(callback)

    def notify_job_start(self, job):
        for callback in self.on_job_starts_callbacks:
            callback(self, job)

    def notify_job_end(self, job):
        for callback in self.on_job_ends_callbacks:
            callback(self, job)

    def notify_xml_render_start(self, job, xml):
        for callback in self.before_xml_render_callbacks:
            callback(self, job, xml)

    def notify_xml_render_end(self, job, xml):
        for callback in self.after_xml_render_callbacks:
            callback(self, job, xml)


class Renderer(MediaInterface, RendererFilterInterface):
    """
        Main engine to convert and ODT document into a jinja
        compatible template.

        Basic use example:
            engine = Renderer()
            result = engine.render(template, var1=val1, var2=val2, ...)


        Renderer provides an environment property which should be used
        to add custom filters to the ODF render.
            engine = Renderer()
            engine.environment.filters['custom_filter'] = filterFn
            result = engine.render('template.odt', var1=val1, ...)
    """

    def __init__(self, environment=None, **kwargs):
        """
        Create a Renderer instance.

        args:
            environment: Use this jinja2 environment. If not specified, we
                         create a new environment for this class instance.

        """
        super(Renderer, self).__init__(**kwargs)
        self.log = logging.getLogger(__name__)
        self.environment = environment or Environment(
            undefined=UndefinedSilently, autoescape=True)

        self.environment.filters['markdown'] = lambda v: v

    def render(self, template, **kwargs):
        """
            Render a template

            args:
                template: A template file. Could be a string or a file instance
                **kwargs: Template variables. Similar to jinja2

            returns:
                A binary stream which contains the rendered document.
        """

        render_job = ODTRender(self, template, **kwargs)
        return render_job.render()