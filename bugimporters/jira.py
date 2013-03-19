# This file is part of OpenHatch.
# Copyright (C) 2010, 2011 Jack Grigg
# Copyright (C) 2010 OpenHatch, Inc.
# Copyright (C) 2012 Berry Phillips.
# Copyright (C) 2012 Asheesh Laroia.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import lxml
import lxml.etree
import urlparse
import logging
import scrapy
from scrapy.selector import XmlXPathSelector
from scrapy.selector import HtmlXPathSelector

import bugimporters.items
from bugimporters.base import BugImporter
from bugimporters.helpers import cached_property, string2naive_datetime
from datetime import timedelta,datetime


class JiraBugImporter(BugImporter):
    def __init__(self, *args, **kwargs):
        # Call the parent __init__.
        super(JiraBugImporter, self).__init__(*args, **kwargs)

        if self.bug_parser is None:
            self.bug_parser = JiraBugImporter

    def process_queries(self, queries):
        for query_url in queries:

            yield scrapy.http.Request(url=query_url,
                    callback=self.handle_query_response)

    def handle_query_response(self, response):
        hxs = HtmlXPathSelector(response)
        #The xpath class search for elements with multiple classes is less the ideal.
        count = int(hxs.select("//span[contains(concat(' ',normalize-space(@class),' '), ' results-count-total ')]/text()").extract()[0])

        #Iterate over the pagination offset. 50 per a page
        for step in range(0, count, 50 ):
            yield scrapy.http.Request(url=response.url + '&startIndex={0}'.format(step),
                    callback=self.process_navigation_page)


    def process_navigation_page(self, response):
        """@todo: Docstring for process_navigation_page

        :response: @todo
        :returns: @todo

        """
        hxs = HtmlXPathSelector(response)
        itemIds = hxs.select("//td[contains(concat(' ',normalize-space(@class),' '), ' issuekey ')]/a/text()").extract()
        for itemId in itemIds:
            yield scrapy.http.Request(
                url= '{0}si/jira.issueviews:issue-xml/{1}/{1}.xml'.format(self.tm.get_base_url(), itemId),
                callback=self.handle_bug_xml)

    def format_date(self, date_string):
        """@todo: Docstring for format_date

        :date_string: @todo
        :returns: @todo

        """
        offset = 0
        try:
            offset = int(date_string[-5:])
        except Exception as e:
            logging.exception(e)
            print "Error"

        delta = timedelta(hours = offset / 100)

        fmt = "%a, %d %b %Y %H:%M:%S"
        time = datetime.strptime(date_string[:-6], fmt)
        time -= delta
        return time

    def handle_bug_xml(self, response):
        logging.info("STARTING XML")
        hxs = XmlXPathSelector(response)
        item = hxs.select('//item')
        try:
            parsed = bugimporters.items.ParsedBug({
                'title': item.select('title/text()').extract()[0],
                'description': item.select('description/text()').extract()[0] ,
                'status':  item.select('status/text()').extract()[0],
                'people_involved': 0, #TODO
                'date_reported': self.format_date(item.select('created/text()').extract()[0]),
                'last_touched': self.format_date(item.select('updated/text()').extract()[0]),
                'submitter_username': item.select('reporter/@username').extract()[0],
                'submitter_realname': item.select('reporter/text()').extract()[0],
                'canonical_bug_link': item.select('link/text()').extract()[0],
                'looks_closed': (item.select('status/text()').extract()[0] == 'Closed'),
                'last_polled': datetime.now(),
                # TODO tracker ids
                #'_project_name': self.tm.tracker_name,
                #'_tracker_name': self.tm.tracker_name,
            })
            yield parsed
        except IndexError as e:
            logging.exception(e)
            logging.debug("AHHHHHHHHHHHHHHHHHHHHHH!!!!!!!!!!!!!: {0}".format(item.select('title/text()').extract()[0]))




