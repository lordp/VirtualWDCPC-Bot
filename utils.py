from datetime import datetime
import logging
import re
from praw.exceptions import APIException


def ordinal(num, name=None):
    suffixes = {1: 'st', 2: 'nd', 3: 'rd'}
    if 10 <= num % 100 <= 20:
        suffix = 'th'
    else:
        suffix = suffixes.get(num % 10, 'th')

    result = str(num) + suffix

    if name is not None and 'tuson' in name.lower():
        result = 'TOP TEN! ({0})'.format(result)

    return result


def is_master(author):
    return author.name == 'lordp' and author.discriminator == '6469'


def find_channel(server_list, server, channel):
    for target in server_list:
        if target.name == server:
            for chan in target.channels:
                if chan.name == channel:
                    return chan

    return None


def adjust_table(table, sort_by='points', reverse=True, is_float=False):
    # Current position (default: first place)
    position = 1
    position_diff = 1

    previous_item = None
    first_item = None

    for index, row in enumerate(sorted(table, key=lambda item: item[sort_by], reverse=reverse)):
        if index == 0:
            row['position'] = 1
            row['diff'] = '-'
            row['relative_diff'] = '-'
            first_item = row
        else:
            if row[sort_by] == previous_item[sort_by]:
                position_diff += 1
            else:
                position += 1
                position_diff = 1

            row['position'] = position

            row['diff'] = row[sort_by] - first_item[sort_by]
            row['relative_diff'] = row[sort_by] - previous_item[sort_by]

            if is_float:
                row['diff'] = round(row['diff'], 3)
                row['relative_diff'] = round(row['relative_diff'], 3)

        previous_item = row

    return table


def format_float(num):
    return format(num, '.15g')


def debug_log(msg):
    formatted_msg = "[{0}]: {1}".format(str(datetime.utcnow()), msg)
    print(formatted_msg)
    logging.info(formatted_msg)


def format_time(seconds):
    m, s = divmod(seconds, 60)
    if m > 0:
        return '{0:.0f}:{1:06.3f}'.format(m, s)
    else:
        return '{0:06.3f}'.format(s)


def calculate_points(position):
    # "Switch" statement with places and points.
    return {
        1: 15,
        2: 12,
        3: 10,
        4: 8,
        5: 6,
        6: 5,
        7: 4,
        8: 3,
        9: 2,
        10: 1
        }.get(position, 0)


def convert_time(lap):
    p = re.compile(r'((\d)[:\.])?([\d\.]+)')
    time = p.match(lap)
    if time.group(2) is None:
        secs = float(time.group(3))
    else:
        secs = float((int(time.group(2)) * 60) + float(time.group(3)))

    return round(secs, 3)


def build_standings_table(mode, standings):
    if mode == 'driver':
        table = ' |Name|Team|Points|\n-|-|-|-\n'
    else:
        table = ' |Name|Points|\n-|-|-\n'

    for idx, row in enumerate(standings[:10]):
        if mode == 'driver':
            table = table + '{index}|{name}|{team}|{points}\n'.format(
                index=idx + 1, name=row['name'], points=row['points'], team=row['team']
            )
        else:
            table = table + '{index}|{name}|{points}\n'.format(
                index=idx + 1, name=row['name'], points=row['points']
            )

    return table


def create_thread(subreddit, title, body):
    try:
        subreddit.submit(title=title, selftext=body, send_replies=False)
        debug_log("New thread posted")
    except APIException:
        debug_log("API Exception raised, unable to create thread")

