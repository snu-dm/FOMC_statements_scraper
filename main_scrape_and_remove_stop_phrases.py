import time, os, re, pickle, argparse, shutil
from bs4 import BeautifulSoup
from datetime import datetime
from glob import glob
from tqdm import tqdm
tqdm.pandas()
import pandas as pd
import requests
from daterangeparser import parse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

parser = argparse.ArgumentParser()
parser.add_argument('--start_mmddyyyy', type=str, default="01/01/1994")
parser.add_argument('--end_mmddyyyy', type=str, default="01/01/2011")
parser.add_argument('--insert_into_NRFDB', type=lambda x: (str(x).lower() == 'true'), default=False)
args = parser.parse_args()

start_mmddyyyy = args.start_mmddyyyy
end_mmddyyyy = args.end_mmddyyyy
insert_into_NRFDB = args.insert_into_NRFDB

chromedriver_filepath = "C:\GIT\SELENIUM_DRIVERS\chromedriver_win32\chromedriver.exe"
save_root_dir = './Statements'
save_temp_dir = './Temp'

url = "https://www.federalreserve.gov/monetarypolicy/materials/"


###########################################################################
#  DATABASE SETTING # START
###########################################################################
import pandas as pd
from sqlalchemy import create_engine, select, delete, insert, update
import config
from schemas import statements
from minio import Minio
from minio.error import S3Error

#Create Engine
engine = create_engine(f'postgresql://{config.user}:{config.pw}@{config.host}:{config.port}/{config.db}')
client = Minio(config.minio_api_endpoint, access_key=config.user, secret_key=config.pw, secure=False)

def extract_begin_end_dates(date_range):
    if '-' not in date_range:
        parsed, _ = parse(date_range)
        return parsed, parsed
    
    elif '/' in date_range:
        begin_month, end_month, begin_date, end_date, year = date_range.replace(',', '').replace('-', ' ').replace('/', ' ').split(' ')
        date_range = f'{begin_month} {begin_date}-{end_month} {end_date}, {year}'
        return parse(date_range)
        
    else:
        return parse(date_range)

def get_insert_query(document_date, meeting_date_start, meeting_date_end, path):
    insert_query = insert(statements).values(
        path=path,
        organization = 'FOMC',
        documentdate = document_date,
        meetingdate_start = meeting_date_start,
        meetingdate_end = meeting_date_end
    )
    return insert_query

###########################################################################
#  DATABASE SETTING # END
###########################################################################

def prepare_resources_for_scraping(chromedriver_filepath, url, start_mmddyyyy, end_mmddyyyy):
    chrome_options = Options()
    chrome_options.headless = True
    driver = webdriver.Chrome(chromedriver_filepath, options=chrome_options)
    driver.get(url)
    time.sleep(5)
    
    # set start date
    start_date = driver.find_element_by_name("startmodel")
    start_date.clear()
    start_date.send_keys(start_mmddyyyy)

    # set end date
    end_date = driver.find_element_by_name("endmodel")
    end_date.clear()
    end_date.send_keys(end_mmddyyyy)

    # select policy statements
    statement_checkbox = driver.find_element_by_xpath("//label/input[contains(..,'Policy Statements')]")
    statement_checkbox.click()

    # apply filter
    submit = driver.find_element_by_css_selector(".btn.btn-primary")
    submit.click()
    
    # get the page control row
    pagination = driver.find_element_by_class_name('pagination')

    # go to the last page to find the largest page number
    last_page = pagination.find_element_by_link_text('Last')
    last_page.click()
    pages = pagination.text.split('\n')
    largest_page = int(pages[-3])
    
    return driver, pagination, largest_page

def extract_meetingdate_documentdate_statementurl(soup):
    meeting_date = soup.select('strong')[0].text
    document_date = soup.select('em')[0].text
    statement_url = 'https://www.federalreserve.gov/{}'.format([item for item in soup.select('a') if 'HTML' in item.text][0]['href'])
    return meeting_date, document_date, statement_url

def scrape_URLs_and_meeting_dates_and_document_dates(driver, pagination, largest_page):
    meeting_date_list, document_date_list, statement_url_list = [], [], []
    # go back to first page and start the loop
    first_page = pagination.find_element_by_link_text('First')
    first_page.click()
    next_page = pagination.find_element_by_link_text('Next')
    
    for _ in range(largest_page):
        driver.find_element_by_css_selector(".panel.panel-default") 
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        
        rows = soup.select('div.row.fomc-meeting')[1:]
        for one_row in rows:
            if one_row.select('.fomc-meeting__month.col-xs-5.col-sm-3.col-md-4')[0].text.strip()=='Statement':
                # Extract statements written in HTML format
                meeting_date, document_date, statement_url = extract_meetingdate_documentdate_statementurl(one_row)
                meeting_date_list.append(meeting_date)
                document_date_list.append(document_date)
                statement_url_list.append(statement_url)
        
        next_page.click()
    print('Number of URLs: {}'.format(len(statement_url_list)))
    
    return statement_url_list, meeting_date_list, document_date_list

def get_text_for_a_statement_from_2006_to_2022(soup):
    return soup.find('div', class_ = 'col-xs-12 col-sm-8 col-md-8').text.strip()

def get_text_for_a_statement_from_1996_to_2005(soup):
    return '\n'.join([item.text.strip() for item in soup.select('table td')])

def get_text_for_a_statement_from_1994_to_1995(soup):
    return soup.find('div', id="content").text.strip()

doublespace_pattern = re.compile('\s+')
def remove_doublespaces(document):
    return doublespace_pattern.sub(' ', document).strip()

stop_phrase_patterns = [re.compile('Release Date: [A-z][a-z]{2,8} \d{1,2}, \d{4}')\
                       , re.compile('For immediate release')\
                       , re.compile('Home \|.*')\
                       , re.compile('\d{4} Monetary policy')\
                       , re.compile('Implementation Note issued.*')\
                       , re.compile('Frequently Asked Questions.*')\
                       , re.compile('For media inquiries.*')\
                       , re.compile('\(\d{1,3} KB PDF\)')]
def remove_stop_phrases(document):
    for stop_phrase_pattern in stop_phrase_patterns:
        document = stop_phrase_pattern.sub(' ', document)
        document = remove_doublespaces(document)
    return document

if __name__ == '__main__':
    
    driver, pagination, largest_page = prepare_resources_for_scraping(chromedriver_filepath, url, start_mmddyyyy, end_mmddyyyy)
    statement_url_list, meeting_date_list, document_date_list = scrape_URLs_and_meeting_dates_and_document_dates(driver, pagination, largest_page)
        
    doc_count = 0
    for statement_url, meeting_date, document_date in tqdm(zip(statement_url_list, meeting_date_list, document_date_list)):
        
        # Scrape statements
        statement_resp = requests.get(statement_url)
        statement_soup = BeautifulSoup(statement_resp.content, 'lxml')

        document_date_yyyymmdd = datetime.strftime(datetime.strptime(document_date, "%B %d, %Y"), "%Y%m%d")
        year = int(document_date_yyyymmdd[:4])
        if year >= 2006:
            doc = get_text_for_a_statement_from_2006_to_2022(statement_soup)
        elif year >=1996:
            doc = get_text_for_a_statement_from_1996_to_2005(statement_soup)
        else:
            doc = get_text_for_a_statement_from_1994_to_1995(statement_soup)
        
        # Clean
        doc = remove_doublespaces(doc)
        
        # Save data
        save_dir = os.path.join(save_root_dir, 'raw', document_date_yyyymmdd[:4])
        if not os.path.exists(save_dir): os.makedirs(save_dir)
        save_filepath = os.path.join(save_dir, '{}.txt'.format(document_date_yyyymmdd))
        with open(save_filepath, "w", encoding='utf-8-sig') as file:
            file.write("MEETING_DATE: {}\n".format(meeting_date))
            file.write(doc)
            doc_count += 1
            
        # Remove stop-phrases
        doc = remove_stop_phrases(doc)
        
        ###########################################################################
        #  INSERT INTO DATABASE # START
        ###########################################################################
        if insert_into_NRFDB:
            with engine.connect() as con:
                document_date = document_date_yyyymmdd
                document = doc

                transactions = con.begin()
                try:
                    meeting_date_start, meeting_date_end = extract_begin_end_dates(meeting_date)
                    meeting_date_start_string = meeting_date_start.strftime("%Y-%m-%d")
                    meeting_date_end_string = meeting_date_end.strftime("%Y-%m-%d")

                    bucket_name = 'monetary-policy'
                    minio_object_name = 'FOMC/Statements/{}/{}.parquet'.format(meeting_date_start_string[:4], meeting_date_start_string)
                    path='{}/{}'.format(bucket_name, minio_object_name)
                    
                    # PostgreSQL
                    insert_query = get_insert_query(document_date, meeting_date_start, meeting_date_end, path)
                    con.execute(insert_query)

                    # S3 (MINIO)
                    df = pd.DataFrame([(document_date, meeting_date_start_string, meeting_date_end_string, document)], \
                                      columns=['documentdate', 'meetingdate_start', 'meetingdate_end', 'document'])
                    local_object_filepath = os.path.join(save_temp_dir, '{}.parquet'.format(document_date))
                    if not os.path.exists(os.path.dirname(local_object_filepath)):
                        os.makedirs(os.path.dirname(local_object_filepath))
                    df.to_parquet(local_object_filepath)
                    client.fput_object(
                        bucket_name, minio_object_name, local_object_filepath,
                    )

                    transactions.commit()
                except:
                    print('Failed to INSERT data: {}'.format(statement_url))
                    transactions.rollback()
        
        ###########################################################################
        #  INSERT INTO DATABASE # END
        ###########################################################################
        
        # Save data
        save_dir = os.path.join(save_root_dir, 'no_stop-phrases', document_date_yyyymmdd[:4])
        if not os.path.exists(save_dir): os.makedirs(save_dir)
        save_filepath = os.path.join(save_dir, '{}.txt'.format(document_date_yyyymmdd))
        with open(save_filepath, "w", encoding='utf-8-sig') as file:
            file.write("MEETING_DATE: {}\n".format(meeting_date))
            file.write(doc)
            doc_count += 1
            
    # To save memory, delete the directory in which the *.parquet files were saved.
    try:
        if os.path.exists(save_temp_dir):
            shutil.rmtree(save_temp_dir)
    except OSError as e: print("Error: %s - %s." % (e.filename, e.strerror))
            
    save_dir = '{}/{}'.format(save_root_dir, 'raw')
    print('Saved {} unique documents under {}'.format(len(glob('{}/*/*.txt'.format(save_dir))), save_dir)) 
    
    save_dir = '{}/{}'.format(save_root_dir, 'no_stop-phrases')
    print('Saved {} unique documents under {}'.format(len(glob('{}/*/*.txt'.format(save_dir))), save_dir)) 
    
    
