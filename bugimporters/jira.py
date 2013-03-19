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

### The design of the BugzillaBugImporter has always been very special.
#
### We get bug data by executing a show_bug.cgi?ctype=xml query against the
### bug tracker in question.
#
### We populate that query with a list of bug IDs that we care about. In
### general, we want to issue fairly few show_bug?ctype=xml queries, just
### to be nice to the remote bug tracker.
#
### This list of bug IDs comes from a few places.
#
### First, and very easily, it comes from the list of bugs we are told
### we already have crawled.
#
### Second, and more complicated: we execute a number of queries against
### the remote bug tracker to get a list of bug IDs we *should* care about.
### This includes queries about bitesize bugs in the remote bug tracker.
### The current implementation takes the approach that, after we finish
### extracting the list of bug IDs we care about, it calls a method to
### enqueue a request (if required) to make sure those bug IDs are fetched.
###
### To avoid duplicates, that method stores some state in the
### BugzillaBugImporter instance to indicate it has queued up a request for
### data on those bugs. That way, if the method is called repeatedly with
### bug IDs which we are in the middle of downloading, we carefully refuse to
### re-download them and waste time on the poor remote bug tracker.

class JiraBugImporter(BugImporter):
    def __init__(self, *args, **kwargs):
        # Call the parent __init__.
        super(JiraBugImporter, self).__init__(*args, **kwargs)

        if self.bug_parser is None:
            self.bug_parser = JiraBugImporter

        # Create a set of bug IDs whose data we have already enqueued
        # a request for.
        self.already_enqueued_bug_ids = set()
        print "ASDFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
        print

    def process_queries(self, queries):
        for query_url in queries:
            # Add the query URL and generic callback.
            # Note that we don't know what exact type of query this is:
            # a tracking bug, or just something that returns Bugzilla XML.
            # We get to disambiguate in the callback.
            print "QUERY!!!!{0}".format(query_url)
            yield scrapy.http.Request(url=query_url,
                    callback=self.handle_query_response)

    def handle_query_response(self, response):

        hxs = HtmlXPathSelector(response)

        print "asdfsdf"
        count = int(hxs.select("//span[contains(concat(' ',normalize-space(@class),' '), ' results-count-total ')]/text()").extract()[0])


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

        #for item in items:

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
        # Turn the string into an XML tree.
            #print item
            #print
        print response.body
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
                #'_project_name': self.tm.tracker_name,
                #'_tracker_name': self.tm.tracker_name,
            })
            print parsed
            yield parsed
        except IndexError as e:
            logging.exception(e)
            logging.debug("AHHHHHHHHHHHHHHHHHHHHHH!!!!!!!!!!!!!: {0}".format(item.select('title/text()').extract()[0]))


    def handle_bug_list_xml_parsed(self, bug_list_xml):
        for bug_xml in bug_list_xml.xpath('bug'):
            error = bug_xml.attrib.get('error', None)
            if error:
                logging.error("Uh, there was one bug (%s) with an error: %s",
                              bug_xml.xpath('bug_id')[0].text,
                              error)
                continue # Skip this bug, since we have an error and no data.

            # Create a BugzillaBugParser with the XML data.
            bbp = self.bug_parser(bug_xml)

            # Get the parsed data dict from the BugzillaBugParser.
            data = bbp.get_parsed_data_dict(base_url=self.tm.get_base_url(),
                                            bitesized_type=self.tm.bitesized_type,
                                            bitesized_text=self.tm.bitesized_text,
                                            documentation_type=self.tm.documentation_type,
                                            documentation_text=self.tm.documentation_text)

            data.update({
                'canonical_bug_link': bbp.bug_url,
                '_tracker_name': self.tm.tracker_name,
                '_project_name': bbp.generate_bug_project_name(
                        bug_project_name_format=self.tm.bug_project_name_format,
                        tracker_name=self.tm.tracker_name),
            })

            yield data


