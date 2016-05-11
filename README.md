# rawdog-html-parser
HTML parser for [rawdog](http://offog.org/git/rawdog/) utility that lets it treat regular webpages as RSS feeds.

Example of HTML feed definition is given below. Only html2rss-related options are shown, of course, you can use anything else your rawdog instance has to offer (like proxying, basic HTTP authorization, and so on).

```
feed 1h http://time.com/newsfeed/
    # This line is needed to enable html2rss engine. If set to anything but 'true', all other html2rss options will be ignored.
    html2rss true
    
    # Should failure to find any articles be treated as an error? 
    # Such thing can happen as a result of unexpected page layout change.
    html2rss.channel.allowempty false
    
    # RSS channel title. You can take text content of certain tags like this.
    html2rss.channel.title /html/head/title/text()
    
    # RSS channel descripton. You can filter tags by their attributes and take values of attributes using @.
    html2rss.channel.description /html/head/meta[@name='description']/@value
    
    # Should we convert description element into text-only string rather than using sanitized HTML?
    html2rss.channel.description.textonly true
    
    # Channel URL - by default it's the URL we download the feed from, but you can choose something different, for example you can parse a simpler printable version of the page and keep the link to the full one. URL will be made absolute.
    html2rss.channel.link //header[@role='banner']//a[@class='logo']/@href
    
    # XPath for article, relative to document root (to simplify other XPaths, and handle articles with missing titles correctly)
    html2rss.item //section[@role='main']//article
    
    # XPath for article title, relative to article node. It can be omitted, but article must have a description then.
    html2rss.item.title ./header/h2[@itemprop='headline']/text()
    
    # XPath for article description, relative to article node. It can be omitted, but article must have a title then.
    html2rss.item.description ./section[@itemprop="articleBody"]
    
    # Should we strip all HTML from item description?
    html2rss.item.description.textonly false
    
    # XPath for article URL, relative to article node. It can be omitted, but then you won't be able to click on the article to see the full version of it. All URLs will be made absolute.
    html2rss.item.link ./footer/div[@class='OUTBRAIN']/@data-src
    
    # XPath for article GUID data, relative to article node. html2rss will calculate MD5 from text data of this node and use it as GUID. It can be omitted. 
    html2rss.item.guid ./@id
    
    # XPath for article date, relative to article node. It does not support parsing natural dates (as in '13 hours ago'). It can be omitted, in which case html2rss will use current time.
    html2rss.item.date .
    
    # Locale for parsing dates, determines which language is used for month names and such.
    html2rss.item.date.locale C
    
    # Format for parsing dates. Same format as used by strptime() function.
    html2rss.item.date.format 
    
    # Space-separated list of tags and attributes(starting with @) to strip out of descriptions that haven't been outright converted to plaintext. Tags are replaced with their inner content, attributes are deleted.
    html2rss.clean strong em blink font h1 h2 h3 h4 h5 h6 @class @style
    
    # If true, html2rss will add some scripting-related tags and attrs to the list above, specifically: 
    # script @onclick @onload @onunload @onmouseenter @onmouseleave
    # It is true by default, so it can be omitted.
    html2rss.clean.scripts true    
```
