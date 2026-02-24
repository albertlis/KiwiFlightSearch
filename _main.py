"""
Legacy script
"""

import io
import logging
import os
import time
import zipfile

import schedule
import yagmail
from dotenv import load_dotenv

from kiwiflight.processing.duration import FlightProcessorDuration
from kiwiflight.scraping.playwright_scraper import PlaywrightScraper


def send_mail(print_info: str) -> None:
    load_dotenv()
    email_subject = 'Loty Kiwi'

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        zipf.writestr('flights.html', print_info.encode('utf-8'))
    zip_buffer.seek(0)
    zip_buffer.name = 'flights.zip'

    yag = yagmail.SMTP(os.getenv('SRC_MAIL'), os.getenv('SRC_PWD'), port=587, smtp_starttls=True, smtp_ssl=False)
    yag.send(
        to=os.getenv('DST_MAIL'), subject=email_subject, contents='Loty Kiwi',
        attachments=[zip_buffer]
    )


def main() -> None:
    iata_list = ['KTW']
    scraper = PlaywrightScraper('marzec', 'czerwiec', iata_list)
    flights_data = scraper.webscrap_flights()

    # with open('date_price_list.pkl', 'rb') as f:
    #     flights_data = pickle.load(f)
    # print(flights_data)
    # flights_processor = FlightProcessorWeekends(500, 10, 11, iata_list)
    flights_processor = FlightProcessorDuration(650, 7, 10, iata_list, start_date="01.02.2026", end_date="01.06.2026")
    print_info = flights_processor.process_flights_info(flights_data)
    with open('flights.html', 'wt', encoding='utf-8') as f:
        f.write(print_info)
    send_mail(print_info)


if __name__ == '__main__':
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    # main()
    schedule.every().day.at("15:30").do(main)
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logging.exception("An error occurred:")
            print(e)
            time.sleep(60 * 60)
        time.sleep(1)
