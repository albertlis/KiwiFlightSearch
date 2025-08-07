import logging
import os
import pickle

import yagmail
from dotenv import load_dotenv

from flights_processor_weekends import FlightProcessorWeekends
from flights_processor_duration import FlightProcessorDuration
from kiwi_scrapper import KiwiScrapper
# from kiwi_scrapper_new import KiwiScrapper


def send_mail(print_info: str) -> None:
    load_dotenv()
    email_subject = 'Loty Kiwi'
    yag = yagmail.SMTP(os.getenv('SRC_MAIL'), os.getenv('SRC_PWD'), port=587, smtp_starttls=True, smtp_ssl=False)
    yag.send(to=os.getenv('DST_MAIL'), subject=email_subject, contents=(print_info, 'text'))


def main() -> None:
    iata_list = ['WRO']
    # iata_list = ['POZ']
    # kiwi_scrapper = KiwiScrapper('wrzesień', 'październik', iata_list)
    # flights_data = kiwi_scrapper.webscrap_flights()

    with open('date_price_list.pkl', 'rb') as f:
        flights_data = pickle.load(f)

    flights_processor = FlightProcessorWeekends(500, 10, 11, iata_list)
    # flights_processor = FlightProcessorDuration(400, 7, 10, iata_list, start_date="28.08.2025", end_date="15.09.2025")
    print_info = flights_processor.process_flights_info(flights_data)
    with open('flights.html', 'wt', encoding='utf-8') as f:
        f.write(print_info)
    # send_mail(print_info)


if __name__ == '__main__':
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    # schedule.every().saturday.at("09:00").do(main)
    # while True:
    #     try:
    #         schedule.run_pending()
    #     except Exception as e:
    #         logging.exception("An error occurred:")
    #         print(e)
    #         time.sleep(60 * 60)
    #     time.sleep(1)
    main()
