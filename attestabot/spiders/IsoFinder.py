from scrapy import Request
from scrapy.spiders import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor
import os, logging
import pandas as pd
from urllib.parse import urlparse
from pdb import set_trace

#MAX_HITS_PER_HOST_PAGE_WITH_KW  = 10
#MAX_HITS_PER_HOST_PAGE_WITH_IMG = 5
MAX_HITS_PER_HOST_TOTAL         = 20
MAX_REQUESTS_PER_HOST           = 700

KEYWORDS_CERTIFICATE_NO_ISO = (
        'zertifikat',
        'zertifizierung',
        'certifica',
        )

KEYWORDS_CERTIFICATE = KEYWORDS_CERTIFICATE_NO_ISO + ('iso',)

ALLOWED_EXTENSIONS = (
        'pdf',
        'png',
        'jpg',
        'jpeg',
        )


class IsoFinder(CrawlSpider):
    name = 'iso-finder'

    custom_settings = {
            'CONCURRENT_REQUESTS'    : 200,
            'DOWNLOAD_DELAY'         : .25,
            #'ROBOTSTXT_OBEY'         : False,
            'DOWNLOAD_TIMEOUT'       : 15,
            'DEPTH_LIMIT'            : 4,
            'DEPTH_PRIORITY'         : 1,
            'SCHEDULER_DISK_QUEUE'   : 'scrapy.squeues.PickleFifoDiskQueue',
            'SCHEDULER_MEMORY_QUEUE' : 'scrapy.squeues.FifoMemoryQueue',
            'COOKIES_ENABLED'        : False,
            'RETRY_ENABLED'          : False,
            }

    rules = [
            Rule(LinkExtractor(), follow=True, callback='parse_item', process_request='process_request'),
            ]


    #placeholder, may be useful in the future
    #def process_links(self, links):
    #    for link in links:
    #        yield link


    def process_request(self, request, response):
        hostname = urlparse(response.request.meta.get('company_homepage')).hostname
        hostname_current = urlparse(response.url).hostname #can be different from hostname because of valid redirects
        if (hostname_current != urlparse(request.url).hostname):
            logging.debug(f'Dropping request to a host different than {hostname_current}: {request.url}.')
            return None
        if sum(self.hit_counter[hostname].values())>MAX_HITS_PER_HOST_TOTAL:
            logging.debug(f'Max hits per host {hostname} exceeded (reached {sum(self.hit_counter[hostname].values())}), dropping new requests.')
            return None
        if self.request_counter[hostname]>=MAX_REQUESTS_PER_HOST:
            logging.debug(f'Max requests ({self.request_counter[hostname]}) reached for {hostname}, dropping new requests.')
            return None
        for attr in ('name', 'company_homepage'):
            request.meta[attr] = response.request.meta.get(attr)
        self.request_counter[hostname] += 1
        return request


    def __init__(self, *args, **kwargs):
        super(IsoFinder, self).__init__(*args, **kwargs)
        self.parquet_file    = kwargs.get('parquet_file')
        self.request_counter = {}
        self.hit_counter     = {}

    def start_requests(self):
        df = pd.read_parquet(self.parquet_file)
        for idx, (name,url) in df.query('url_exists=="TRUE"')[['name','url']].iterrows():
        #for url in (
        #        'https://wettstein-produktion.ch/', # ok
        #        'https://juice.world/', #ok
        #        'http://www.designwerk.com/', #error 510
        #        'https://www.alz-maschinen.ch/', #ok, needs DEPTH_LIMIT=2
        #        'https://aa-praezisionsmechanik.ch/', #no: contains only a png with no keyword in the file name and no reference to keywords in the text
        #        'https://www.almutechag.ch/', #ok
        #        'https://www.blue-o.ch/', #ok
        #        'https://www.hjakober.ch/', #ok
        #        'https://www.enzler.com', #ok, needs DEPTH_LIMIT=3
        #        'https://www.brtec.ch/', #ok
        #        'https://www.guyan-trans.ch', #ok, finds pdfs and keywords but no logos
        #        'https://www.swissestetic.ch/', #error 510
        #        'https://realestate-ch.apleona.com/', #ok, needs DEPTH_LIMIT=4 for pdfs
        #        'https://joos-metallbau.ch', #ok
        #        'https://www.blumatech.ch/', #ok
        #        'https://www.schmidlinag.ch', #ok
        #        'https://www.leuthold-metallbau.ch', #ok
        #        'http://www.belloli.ch', #ok
        #        'https://www.rinoweder.ch/', #ok, false positive images with 'Janisol' in the name
        #        'https://www.kazi-metall.ch', #ok but very slow, works with with breadth-first-order search and MAX_REQUESTS_PER_HOST
        #        'https://contreag.ch/', #ok
        #        'https://www.new-process.ch', #ok
        #        'https://www.weita.ch', #ok but very slow
        #        'https://www.airproduct.ch', #ok
        #        'https://schmid-terewa.ch/', #error 510
        #        ):
            hostname = urlparse(url).hostname
            self.request_counter[hostname] = 0
            self.hit_counter[hostname]     = {
                    'page_with_file' : 0,
                    'page_with_kw'   : 0,
                    'page_with_logo' : 0,
                    }
            meta = {
                    #'name'      : hostname, #FIXME
                    'name'             : name,
                    'company_homepage' : url,
                    }
            logging.info(f'Submitting {url=} with {hostname=}')
            yield Request(url, meta=meta)

    def parse_item(self, response):
        if hasattr(response, 'text'):
            item = {
                    'parquet_file'          : self.parquet_file,
                    'name'                  : response.meta['name'],
                    'company_homepage'      : response.meta['company_homepage'],
                    'suburl_with_iso_info'  : response.url,
                    'suburl_has_iso_file'   : 'FALSE',
                    'suburl_is_iso_file'    : 'FALSE',
                    'suburl_has_keyword'    : 'FALSE',
                    'suburl_has_logo'       : 'FALSE',
                    }
            #hostname = urlparse(response.url).hostname
            hostname = urlparse(response.meta['company_homepage']).hostname
            if sum(self.hit_counter[hostname].values())<MAX_HITS_PER_HOST_TOTAL:
                if any(files := [link for link in response.css('*::attr(href)').getall() if (urlparse(link).path.lower().endswith(ALLOWED_EXTENSIONS) and any(kw in link.lower() for kw in KEYWORDS_CERTIFICATE))]):
                    self.hit_counter[hostname]['page_with_file'] += 1
                    item['suburl_has_iso_file'] = 'TRUE'
                if any(text for text in response.css('*::text').getall() if (
                        ' ISO ' in text
                        or text.startswith('ISO ')
                        or text.endswith((' ISO', 'ISO.'))
                        or any(kw in text.lower() for kw in KEYWORDS_CERTIFICATE_NO_ISO)
                        )):
                    self.hit_counter[hostname]['page_with_kw'] += 1
                    #if self.hit_counter[hostname]['page_with_kw']<=MAX_HITS_PER_HOST_PAGE_WITH_KW:
                    logging.debug(f'found page with keyword at {response.url}')
                    item['suburl_has_keyword'] = 'TRUE'
                if any(link for link in response.css('img').xpath('@src').getall() if any(kw in link.lower() for kw in KEYWORDS_CERTIFICATE)):
                    self.hit_counter[hostname]['page_with_logo'] += 1
                    #if self.hit_counter[hostname]['page_with_logo']<=MAX_HITS_PER_HOST_PAGE_WITH_IMG:
                    logging.debug(f'found page with logo at {response.url}')
                    item['suburl_has_logo'] = 'TRUE'
                if 'TRUE' in (item['suburl_has_iso_file'], item['suburl_has_keyword'], item['suburl_has_logo']):
                    yield item
                if files:
                    item['suburl_is_iso_file']  = 'TRUE'
                    item['suburl_has_iso_file'] = 'FALSE'
                    item['suburl_has_keyword']  = 'FALSE'
                    item['suburl_has_logo']     = 'FALSE'
                    for link_to_file in files:
                        item['suburl_with_iso_info'] = response.urljoin(link_to_file)
                        yield item

    def parse_start_url(self, response):
        return self.parse_item(response)
