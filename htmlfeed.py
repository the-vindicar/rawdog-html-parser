'''
RAWDOG plugin that allows you to treat HTML pages as RSS feeds.
This plugin uses XPath expressions to describe page layout. 
It also supports tag sanitizing and generating GUIDs for individual items based on their content.
Example feed definition (all rawdog feed parameters work too!):

feed 1h http://time.com/newsfeed/
    # needed to enable htmlfeed engine
    html2rss true   
    # RSS channel title. You can take text value of certain tags like this. 
    html2rss.channel.title /html/head/title/text()      
    # RSS channel descripton. You can filter tags by their attributes and take values of attributes using @.
    html2rss.channel.description /html/head/meta[@name='description']/@value    
    # Should we convert description element into text-only string.
    html2rss.channel.description.textonly true
    # channel URL - by default one we download it by
    html2rss.channel.link //header[@role='banner']//a[@class='logo']/@href
    # if failure to find any articles should be treated as error (it can be result of target site's layout change)
    html2rss.channel.allowempty false
    # XPath for article, relative to document root (to simplify other XPaths, and handle articles with missing titles correctly)
    html2rss.item //section[@role='main']//article
    # XPath for article title, relative to article node
    # Can be omitted, but article must have description then.
    html2rss.item.title ./header/h2[@itemprop='headline']/text()
    # XPath for article description, relative to article node
    # Can be omitted, but article must have title then.
    html2rss.item.description ./section[@itemprop="articleBody"]
    # should we strip all HTML from item description
    html2rss.item.description.textonly false
    # XPath for article URL, relative to article node. Can be skipped.
    html2rss.item.link ./footer/div[@class='OUTBRAIN']/@data-src
    # XPath for article GUID data, relative to article node. html2rss will calculate MD5 from text data and use it as GUID. Can be omitted. 
    html2rss.item.guid ./@id
    # XPath for article date, relative to article node. It does not support parsing natural dates. Can be omitted, html2rss will assume current date.
    html2rss.item.date .
    # locale for parsing dates, determines which language is used for month names and such.
    html2rss.item.date.locale C
    # format for parsing dates. Same format as used by strptime() function.
    html2rss.item.date.format 
    # Space-separated list of tags and attributes(starting with @) to strip out of descriptions that haven't been converted to plaintext. 
    # Tags are replaced with their inner content, attributes are deleted.
    html2rss.clean strong em blink font h1 h2 h3 h4 h5 h6 @class @style
    # If true, html2rss will add some scripting-related tags and attrs to the list above
    html2rss.clean.scripts true    
'''
from copy import deepcopy
from io import BytesIO
import gzip
import hashlib
import urllib2
import lxml.html, lxml.etree

import locale
import threading
from datetime import datetime
from contextlib import contextmanager

#snippet I found that lets you parse date in different locale in a thread-safe manner
LOCALE_LOCK = threading.Lock()
@contextmanager
def setlocale(name):
    with LOCALE_LOCK:
        saved = locale.setlocale(locale.LC_ALL)
        try:
            yield locale.setlocale(locale.LC_ALL, name)
        finally:
            locale.setlocale(locale.LC_ALL, saved)
#
def parseDate(localename, fmt, datestr):
    try:
        with setlocale(localename):
            dateobj = datetime.strptime(fmt[1], datestr)
        return dateobj
    except:
        return None
#
nop = lambda x: None

class ResponseWrapper(object):
    '''This class imitates urllib2's file-like Response object, letting wrapper() perform the actual stream transformation.
    wrapper() is expected to accept two parameters: Response object and Response.info(). 
    wrapper() is expected to return a 2-tuple of new file-like object and modified info.'''
    def __init__(self, original, wrapper):
        self.url = original.url
        self.code = original.code
        self.msg = original.msg
        self._buffer, self._info = wrapper(original, original.info())
    #Response imitation methods
    def read(self, size=-1):
        return self._buffer.read(size)
    def geturl(self):
        return self.url
    def info(self):
        return self._info
    def getcode(self):
        return self.code
    def tell(self):
        return self._buffer.tell()
    def close(self):
        return self._buffer.close()
#

class HTML2RSSProcessor(urllib2.BaseHandler):
    '''urllib2 hook that wraps response into the wrapper above.'''
    _prefix = 'html2rss.'
    def __init__(self, config, feed):
        #we strip the prefix from config options we got from rawdog for convenience sake
        self._params = {
            key[len(self._prefix):] : feed.args[key] 
            for key in filter(lambda x:x.startswith(self._prefix), feed.args.keys()) 
            }
    #
    def _modifyResponse(self, request, response):
        return ResponseWrapper(response, self._parse)
    #
    http_response = _modifyResponse
    https_response = _modifyResponse
    ftp_response = _modifyResponse
    file_response = _modifyResponse
    
    def _parse(self, original, info):
        try:
            #default values
            params = {
                #channel title
                'channel.title' : "/html/head/title/text()",
                #channel description
                'channel.description' : "/html/head/meta[@name='description']/@value",
                #should we strip all HTML from channel description
                'channel.description.textonly' : 'false',
                #channel URL - by default one we download it by
                'channel.link' : lambda x: original.url,
                #if empty match for articles should be treated as error (it can be result of target site's layout change)
                'channel.allowempty' : 'false',
                #XPath for article, relative to document root (to simplify other XPaths, and handle articles with missing titles correctly)
                'item' : nop,
                #XPath for article title, relative to article node
                'item.title' : nop,
                #XPath for article description, relative to article node
                'item.description' : nop,
                #should we strip all HTML from item description
                'item.description.textonly' : 'false',
                #XPath for article URL, relative to article node
                'item.link' : nop,
                #XPath for article guid, relative to article node
                'item.guid' : nop,
                #XPath for article date, relative to article node
                'item.date' : nop,
                #locale for parsing dates
                'item.date.locale' : 'C',
                #format for parsing dates
                'item.date.format' : '',
                #tags and attributes to strip out of descriptions
                'clean' : '',
                #add some scripting-related tags and attrs to the list above
                'clean.scripts' : 'true',
                }
            #import actual config (not a rawdog config)
            params.update(self._params)
            #convert strings in certain parameters into XPath
            for key in (
                'channel.title',
                'channel.description', 
                'channel.link',
                'item',
                'item.title',
                'item.description',
                'item.link',
                'item.date',
                'item.guid',
                ):
                params[key] = lxml.etree.XPath(params[key], smart_strings=False) if isinstance(params[key], basestring) else params[key]
            #some defaults for stripping tags
            if params['clean.scripts']=='true':
                params['clean'] += ' script @onclick @onload @onunload @onmouseenter @onmouseleave'
            #parsing "things to strip" line: attrs start with @, tags don't
            params['clean'] = filter( (lambda x:x), params['clean'].split() )
            params['clean.tags'] = filter(lambda x:not x.startswith('@'), params['clean'])
            params['clean.attrs'] = map(lambda x:x[1:], filter(lambda x:x.startswith('@'), params['clean']))
            #!!!
            #load and parse tree - original is SUPPOSED to contain plaintext reply here.
            if info.get('Content-Encoding','') == 'gzip':
                fileobj = gzip.GzipFile(mode='rb', fileobj=BytesIO(original.read()))
                del info['Content-Encoding']
            else:
                fileobj = original
            htmltree = lxml.html.parse(fileobj)
            #fixing up links
            htmltree.getroot().make_links_absolute(original.url)
            #creating resulting RSS tree
            rss = lxml.etree.XML('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"></rss>')
            channel = lxml.etree.SubElement(rss, 'channel')
            #setting some channel information, if we can find it and it's not empty
            self._addIf(channel, 'title', self._textualize(params['channel.title'](htmltree)))
            if params['channel.description.textonly'] == 'true':
                self._addIf(channel, 'description', 
                    self._textualize(params['channel.description'](htmltree))
                    )
            else:
                self._addIf(channel, 'description', 
                    self._import(params['channel.description'](htmltree), params['clean.tags'], params['clean.attrs'])
                    )
            self._addIf(channel, 'link', self._textualize(params['channel.link'](htmltree)))
            #looking for items and generating error if it's empty
            founditems = params['item'](htmltree)
            if (params['channel.allowempty'] != 'true') and (len(founditems) == 0):
                raise URLError('No items found in the feed '+original.url)
            #item loop for every scpecified item we've found in the page
            for htmlitem in founditems:
                #we try to extract the items
                title = self._textualize(params['item.title'](htmlitem))
                if params['item.description.textonly'] == 'true':
                    description = self._textualize(params['item.description'](htmlitem))
                else:
                    description = self._import(params['item.description'](htmlitem), params['clean.tags'], params['clean.attrs'])
                link = self._textualize(params['item.link'](htmlitem))
                rawguidtext = self._textualize(params['item.guid'](htmlitem))
                if (rawguidtext):
                    md5 = hashlib.md5()
                    md5.update(rawguidtext)
                    guid = md5.digest()
                    del md5
                else:
                    guid = None
                #parsing date. really shitty code that can't handle those popular "X hours ago" timestamps, but it's the best I can do 
                try:
                    date = self._textualize(params['item.date'](htmlitem))
                    date = parseDate(params['item.date.locale'], params['item.date.format'], date) if date else None
                    with setlocale('C'):
                        date = date.strftime('%a, %d %b %Y %H:%M:%S %z') if date else ''
                except ValueError:
                    date = ''
                #if we have at least something
                if (title or description):
                    #making an item
                    rssitem = lxml.etree.SubElement(channel, 'item')
                    self._addIf(rssitem, 'title', title)
                    self._addIf(rssitem, 'description', description)
                    self._addIf(rssitem, 'link', link)
                    self._addIf(rssitem, 'guid', guid)
                    self._addIf(rssitem, 'pubDate', date)
            #done with the loop, finalization
            newbuffer = BytesIO()
            #dumping resulting XML tree into the buffer (prettyprinting not necessary)
            rss.getroottree().write(newbuffer, xml_declaration=True, encoding='utf-8', pretty_print=True)
            #fixing Content-Length and Content-Type, just in case.
            size = newbuffer.tell()
            newbuffer.seek(0, 0)
            info['Content-Length'] = str(size)
            info['Content-Type'] = 'application/rss+xml;charset=UTF-8'
        except Exception as E:
            raise URLError("Feed parsing failed: "+repr(E))
        else:
            return newbuffer, info
    #
    #adds <tag>value</tag> to the parent node if the value is not empty
    def _addIf(self, parent, tag, value):
        if not value:
            return None
        item = lxml.etree.SubElement(parent, tag)
        item.text = value
        return item
    #
    #takes the specified node, and if it's a node, strips it's children from banned tags/attrs and transfroms them into XML-escaped string - for <description>
    def _import(self, value, striptags, stripattrs):
        value = deepcopy(value)
        convert = lambda ele:u''.join( map( (lambda e:lxml.html.tostring(e, encoding='unicode')), ele.iterchildren() ) )
        if value is None:
            return u''
        elif isinstance(value, basestring):
            return unicode(value)
        elif isinstance(value, lxml.etree._Element):
            if striptags:
                lxml.etree.strip_tags(value, *striptags)
            if stripattrs:
                lxml.etree.strip_attributes(value, *stripattrs)
            return convert(value)
        elif isinstance(value, list):
            return u''.join(self._import(v, striptags, stripattrs) for v in value)
        else:
            return repr(value)
    #
    #transforms the value into a text string, no matter what it is
    def _textualize(self, value):
        if value is None:
            return u''
        elif isinstance(value, basestring):
            return unicode(value)
        elif isinstance(value, lxml.etree._Element):
            return value.text
        elif isinstance(value, list):
            return u''.join(self._textualize(v) for v in value)
        else:
            return repr(value)
    #
#
#rawdog hook to get our handler going
def add_urllib2_handlers(rawdog, config, feed, handlers):
    if feed.args.get('html2rss', 'false') == 'true':
        handlers.append(HTML2RSSProcessor(config, feed))
#
#setting the hook
import rawdoglib.plugins
rawdoglib.plugins.attach_hook('add_urllib2_handlers', add_urllib2_handlers)
