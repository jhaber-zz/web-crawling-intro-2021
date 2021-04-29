"""
Iterate over a CSV of URLs, recursively gather their within-domain links, parse the text of each page, and save to file

CSV is expected to be structured with a unique ID (for schools this is called NCES school number or NCESSCH) and URL like so:

|               NCESSCH | URL                                                      |
|----------------------:|:---------------------------------------------------------|
|   1221763800065630210 | http://www.charlottesecondary.org/                       |
|   1223532959313072128 | http://www.kippcharlotte.org/                            |
|   1232324303569510400 | http://www.socratesacademy.us/                           |
|   1226732686900957185 | https://ggcs.cyberschool.com/                            |
|   1225558292157620224 | http://www.emmajewelcharter.com/pages/Emma_Jewel_Charter |

USAGE
    Pass in the start_urls from a a csv file.
    For example, within web-crawling-intro-sp21/day-2/tutorial/tutorial, run:
    
        scrapy crawl textspider -a domain_list=spiders/test_urls.csv
        
    To append output to a file, run:
        
        scrapy crawl textspider -a domain_list=spiders/test_urls.csv -o textspider_output.json
   
    This output can be saved into other file types as well.
    
    NOTE: -o will APPEND output. This can be misleading(!) when debugging since the output
          file may contain more than just the most recent output.

    # Run spider with logging, and append to an output JSON file
    scrapy runspider recursive_text_spider.py \
        -o school_output_test.json \
        -a domain_list=test_urls.csv \
        --loglevel INFO \
        --logfile textspider_tutorial.log

    # Run spider in the background with `nohup`
    nohup scrapy runspider recursive_text_spider.py \
        -o school_output_test.json \
        -a domain_list=test_urls.csv \
        --loglevel INFO \
        --logfile textspider_tutorial.log &
"""

# Install libraries
import tldextract
import csv, re
from bs4 import BeautifulSoup # BS reads and parses even poorly/unreliably coded HTML 
from bs4.element import Comment # helps with detecting inline/junk tags when parsing with BS
import lxml # fast bs4 parser
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import Rule, CrawlSpider

from project.items import ProjectItem # update to reflect name of project

# Define inline tags for cleaning HTML via blacklist
inline_tags = ["b", "big", "i", "small", "tt", "abbr", "acronym", "cite", "dfn", "kbd", 
               "samp", "var", "bdo", "map", "object", "q", "span", "sub", "sup", "head", 
               "title", "[document]", "script", "style", "meta", "noscript"]


class RecursiveTextSpider(CrawlSpider):
    name = 'textspider'
    rules = [
        Rule(
            LinkExtractor(
                canonicalize=False,
                unique=True
            ),
            follow=True,
            callback="parse_items"
        )
    ]
    
    
    def __init__(self, domain_list=None, *args, **kwargs):
        """
        Overrides default constructor to set custom
        instance attributes.
        
        Parameters:
        - domain_list: csv or tsv format
            List of entities containing string domains and unique identifiers.
            
        Attributes:
        
        - start_urls:
            Used by scrapy.spiders.Spider. A list of URLs where the
            spider will begin to crawl.

        - allowed_domains:
            Used by scrapy.spiders.Spider. An optional list of
            strings containing domains that this spider is allowed
            to crawl.

        - domain_to_id:
            A custom attribute used to map a string domain to
            a number representing the unique id defined by
            csv_input.
        """
        super(RecursiveTextSpider, self).__init__(*args, **kwargs)
        self.start_urls = []
        self.allowed_domains = []
        self.rules = (Rule(CustomLinkExtractor(allow_domains = self.allowed_domains), follow=True, callback="parse_items"),)
        self.domain_to_id = {}
        self.init_from_domain_list(domain_list)
    
    
    # Method for parsing items
    def parse_items(self, response):
        
        item = ProjectItem()
        item['url'] = response.url
        item['text'] = self.get_text(response)
        domain = self.get_domain(response.url)    

        item['unique_id'] = self.domain_to_id[domain]
        item['depth'] = response.request.meta['depth'] # uses DepthMiddleware
        print("Depth: ", item['depth'])

        yield item    
        
        
    def init_from_domain_list(self, domain_list):
        """
        Generate's this spider's instance attributes
        from the input domain list, formatted as a CSV or TSV.
        
        Domain List's format:
        1. The first row is meta data that is ignored.
        2. Rows in the csv are 1d arrays with one element.
        ex: row == ['3.70014E+11,http://www.charlottesecondary.org/'].
        
        Note: start_requests() isn't used since it doesn't work
        well with CrawlSpider Rules.
        
        Args:
            domain_list: Is the path string to this file.
        Returns:
            Nothing is returned. However, start_urls,
            allowed_domains, and domain_to_id are initialized.
        """
        if not domain_list:
            return
        with open(domain_list, 'r') as f:
            delim = "," if "csv" in domain_list else "\t"
            reader = csv.reader(f, delimiter=delim, quoting=csv.QUOTE_NONE)
            first_row = True
            for raw_row in reader:
                if first_row:
                    first_row = False
                    continue
                
                unique_id, url = raw_row
                domain = self.get_domain(url, True)
                
                # set instance attributes
                self.start_urls.append(url)
                self.allowed_domains.append(domain)
                self.domain_to_id[domain] = float(unique_id)

    
    def get_domain(self, url, init = False):
        """
        Given the url, gets the top level domain using the
        tldextract library.
        
        Args:
            init (Boolean): True if this function is called while initializing the Spider, else False
        Ex:
        >>> get_domain('http://www.charlottesecondary.org/')
        charlottesecondary.org
        >>> get_domain('https://www.socratesacademy.us/our-school')
        socratesacademy.us
        """
        extracted = tldextract.extract(url)
        permissive_domain = f'{extracted.domain}.{extracted.suffix}' # gets top level domain: very permissive crawling
        specific_domain = re.sub(r'https?\:\/\/w{0,3}\.?', '', url) # full URL without http and www. to compare w/ permissive
        #print("Permissive:", permissive_domain)
        #print("Specific:", specific_domain)
        top_level = len(specific_domain.replace("/", "")) == len(permissive_domain) # compare specific and permissive domain
        
        if init: # Check if this is the initialization period for the Spider.
            if top_level:
                return permissive_domain
            else:
                return specific_domain
        
        # second round
        if permissive_domain in self.allowed_domains:
            return permissive_domain
        
    
    def get_text(self, response):
        """
        Gets the readable text from a website's body and filters it.
        Ex:
        if response.body == "\u00a0OUR \tSCHOOL\t\t\tPARENTSACADEMICSSUPPORT \u200b\u200bOur Mission"
        >>> get_text(response)
        'OUR SCHOOL PARENTSACADEMICSSUPPORT Our Mission'
        
        For another example, see filter_text_ex.txt
        
        More options for cleaning HTML: 
        https://stackoverflow.com/questions/699468/remove-html-tags-not-on-an-allowed-list-from-a-python-string/812785#812785
        Especially consider: `from lxml.html.clean import clean_html`
        """
        # Load HTML into BeautifulSoup, extract text
        soup = BeautifulSoup(response.body, 'html5lib') # slower but more accurate parser for messy HTML # lxml faster
        # Remove non-visible tags from soup
        [s.decompose() for s in soup(inline_tags)] # quick method for BS
        # Extract text, remove <p> tags
        visible_text = soup.get_text(strip = False) # get text from each chunk, leave unicode spacing (e.g., `\xa0`) for now to avoid globbing words
        
        # Remove ascii (such as "\u00")
        filtered_text = visible_text.encode('ascii', 'ignore').decode('ascii')
        
        # Remove ad junk
        filtered_text = re.sub(r'\b\S*pic.twitter.com\/\S*', '', filtered_text) 
        filtered_text = re.sub(r'\b\S*cnxps\.cmd\.push\(.+\)\;', '', filtered_text) 
        # Replace all consecutive spaces (including in unicode), tabs, or "|"s with a single space
        filtered_text = regex.sub(r"[ \t\h\|]+", " ", filtered_text)
        # Replace any consecutive linebreaks with a single newline
        filtered_text = regex.sub(r"[\n\r\f\v]+", "\n", filtered_text)
        # Remove json strings: https://stackoverflow.com/questions/21994677/find-json-strings-in-a-string
        filtered_text = regex.sub(r"{(?:[^{}]*|(?R))*}", " ", filtered_text)

        # Remove white spaces at beginning and end of string; return
        return filtered_text.strip()
