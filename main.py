import os

import yagmail
from dotenv import load_dotenv

from flights_processor import FlightProcessor
from kiwi_scrapper import KiwiScrapper


def send_mail(print_info: str) -> None:
    load_dotenv()
    email_subject = 'Loty Kiwi'
    yag = yagmail.SMTP(os.getenv('SRC_MAIL'), os.getenv('SRC_PWD'), port=587, smtp_starttls=True, smtp_ssl=False)
    yag.send(to=os.getenv('DST_MAIL'), subject=email_subject, contents=(print_info, 'text'))


def main() -> None:
    kiwi_scrapper = KiwiScrapper('marzec', 'czerwiec', ['POZ', 'WRO'])
    flights_data = kiwi_scrapper.webscrap_flights()

    flights_processor = FlightProcessor()
    print_info = flights_processor.process_flights_info(flights_data)
    with open('flights.txt', 'wt', encoding='utf-8') as f:
        f.write(print_info)
    # send_mail(print_info)


if __name__ == '__main__':
    # logging.basicConfig(filename='error.log', level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
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
