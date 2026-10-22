"""Run from project root: python -m tests.test_nm_fill
Starts a local HTTP server and fills only the first two captured NM tabs.
No OpenAI calls, no eCrash access, no real report data.
"""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from playwright.sync_api import sync_playwright
from app.browser.engine import fill_form

ROOT=Path(__file__).resolve().parents[1]
MOCK=ROOT/'mock'/'nm'

def main():
    if not (MOCK/'index.html').exists():
        raise SystemExit('Missing mock/nm/index.html')
    handler=functools.partial(SimpleHTTPRequestHandler,directory=str(MOCK))
    server=ThreadingHTTPServer(('127.0.0.1',0),handler)
    Thread(target=server.serve_forever,daemon=True).start()
    payload={'incident':{'report_identifier_1':'TEST-NM-001','incident_city':'TESTCITY'},'units':[
        {'driver':{'first_name':'DRIVERONE','last_name':'TEST','city':'TESTCITY','state':'NM','zip_code':'87121'},'owner':{'first_name':'OWNERONE','last_name':'TEST','home_phone':'505 111-2222'},'vehicle':{'tag_number':'TEST1','insurance_carrier':'TESTINS1'}},
        {'driver':{'first_name':'DRIVERTWO','last_name':'TEST','city':'TESTCITY','state':'NM','zip_code':'87124'},'owner':{'first_name':'OWNERTWO','last_name':'TEST','home_phone':'505 333-4444'},'vehicle':{'tag_number':'TEST2','insurance_carrier':'TESTINS2'}}]}
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=False)
            page=browser.new_page()
            page.goto(f'http://127.0.0.1:{server.server_address[1]}/index.html')
            warnings=fill_nm_form(page,payload)
            print('Warnings:')
            for warning in warnings:print('-',warning)
            print('Review Unit 1 and Unit 2; close Inspector to exit.')
            page.pause()
            browser.close()
    finally:
        server.shutdown()

if __name__=='__main__':main()

