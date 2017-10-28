from datetime import datetime
import logging
import re
import json
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


def build_standings_table(standings):
    table = ['Pos|Name|Team|Points', ':-:|-|-|:-:']
    if 'team' in standings:
        table[0] += '|||Pos|Name|Points'
        table[1] += '|-|-|:-:|-|:-:'

    top_ten = sorted(standings['driver'][:10], key=lambda item: float(item['points']), reverse=True)
    for idx, row in enumerate(top_ten):
        table.append('{index}|{name}|{team}|{points}'.format(
            index=idx + 1,
            name=row['name'],
            points=format_float(row['points']),
            team=row['team']
        ))
        if 'team' in standings:
            table[idx + 2] += '|||{index}|{name}|{points}'.format(
                index=idx + 1,
                name=standings['team'][idx]['name'],
                points=format_float(standings['team'][idx]['points'])
            )

    return '\n'.join(table)


def create_thread(subreddit, title, body):
    try:
        subreddit.submit(title=title, selftext=body, send_replies=False)
        debug_log("New thread posted")
    except APIException:
        debug_log("API Exception raised, unable to create thread")


def find_driver(name, drivers):
    try:
        driver = next(item for item in drivers if item["name"].lower() == name.lower())
    except StopIteration:
        # filter out all the drivers without an alias
        drivers = filter(lambda x: x['alias'] is not None, drivers)
        driver = next(item for item in drivers if item["alias"].lower() == name.lower())

    return driver


def country_to_flag(country):
    return {
        'Australia': 'australia',
        'Austria': 'austria',
        'Belgium': 'belgium',
        'Bahrain': 'bahrain',
        'Brazil': 'brazil',
        'Canada': 'canada',
        'China': 'china',
        'European Union': 'EU',
        'France': 'france',
        'Germany': 'germany',
        'Hungary': 'hungary',
        'India': 'india',
        'Italy': 'italy',
        'Japan': 'japan',
        'Korea': 'korea',
        'Monaco': 'monaco',
        'Malaysia': 'malaysia',
        'New Zealand': 'nz',
        'Russia': 'russia',
        'Spain': 'spain',
        'Switzerland': 'switzerland',
        'United Kingdom': 'uk',
        'USA': 'us',
        'Singapore': 'singapore',
        'Luxembourg': 'lux',
        'Abu Dhabi': 'UAE',
        'Lithuania': 'lit',
        'Sweden': 'sweden',
        'Finland': 'finland',
        'Norway': 'norway',
        'The Netherlands': 'dutch',
        'Greece': 'greece',
        'Ireland': 'eire',
        'Scotland': 'scotland',
        'Portugal': 'portugal',
        'Poland': 'poland',
        'Hong Kong': 'HK',
        'Malta': 'malta',
        'Indonesia': 'indonesia',
        'Denmark': 'denmark',
        'Azerbaijan': 'azerbaijan',
        'Mexico': 'mexico',
    }.get(country, None)


def save_times(title, times):
    round_number = re.sub(r'[^0-9]', '', title)
    try:
        with open('tt-leaderboard.json', 'r') as infile:
            leaderboard = json.load(infile)
    except FileNotFoundError:
        leaderboard = {
            "total": {}
        }

    leaderboard[round_number] = times
    leaderboard['total'] = generate_leaderboard(leaderboard)

    with open('tt-leaderboard.json', 'w') as outfile:
        json.dump(leaderboard, outfile)


def load_times(title):
    round_number = re.sub(r'[^0-9]', '', title)
    try:
        with open('tt-leaderboard.json', 'r') as infile:
            leaderboard = json.load(infile)
    except FileNotFoundError:
        leaderboard = {
            "total": {}
        }

    if round_number in leaderboard:
        times = leaderboard[round_number]
    else:
        times = []

    return times


def generate_leaderboard(leaderboard):
    total = {}
    for round_number in leaderboard:
        if round_number == 'total':
            continue

        for driver in leaderboard[round_number]:
            if driver['name'] not in total:
                total[driver['name']] = 0

            total[driver['name']] += calculate_points(driver['position'])

    return total
