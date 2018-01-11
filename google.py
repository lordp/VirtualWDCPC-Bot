from __future__ import print_function
import httplib2
import os

from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage

from datetime import datetime, timedelta
from utils import ordinal, calculate_points

from collections import Counter
from pprint import pprint

try:
    import argparse
    # flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
except ImportError:
    flags = None

# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/sheets.googleapis.com-python-quickstart.json
SCOPES = 'https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/spreadsheets.readonly'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'VirtualWDCPC Discord Bot'


class GoogleRequests:
    def __init__(self, cache):
        self.cache = cache
        self.credentials = self.get_credentials()
        self.http = self.credentials.authorize(httplib2.Http())

        self.sheets_url = 'https://sheets.googleapis.com/$discovery/rest?version=v4'
        self.sheets_id = '1i1bpedNBJRW65sX0f4Qf_Z1HFR-6UD3pX-iu0DJHsvc'
        self.sheets_service = discovery.build('sheets', 'v4', http=self.http, discoveryServiceUrl=self.sheets_url)
        self.sheets_ranges = {
            'driver': 'A3:D22',
            'team': 'A28:D38',
            'results': 'B3:U22',
            'driver_standings': 'B3:U22',
            'team_standings': 'B28:E38'
        }

        self.calendar_ids = {
            'f1': 'addict.net.nz_blnvs04jedcsl92g4bfb73tbe8@group.calendar.google.com',
            'fsr': 'addict.net.nz_1n55gt9qm6dc015m9c7qjub1r8@group.calendar.google.com'
        }

        self.leagues = {
            '1400': {
                'drivers': [],
                'teams': []
            },
            '1700': {
                'drivers': [],
                'teams': []
            },
            '2100': {
                'drivers': [],
                'teams': []
            }
        }

    @staticmethod
    def get_credentials():
        """Gets valid user credentials from storage.
    
        If nothing has been stored, or if the stored credentials are invalid,
        the OAuth2 flow is completed to obtain the new credentials.
    
        Returns:
            Credentials, the obtained credential.
        """
        home_dir = os.path.expanduser('~')
        credential_dir = os.path.join(home_dir, '.credentials')
        if not os.path.exists(credential_dir):
            os.makedirs(credential_dir)
        credential_path = os.path.join(credential_dir, 'vwdcpcbot.json')

        store = Storage(credential_path)
        credentials = store.get()
        if not credentials or credentials.invalid:
            flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
            flow.user_agent = APPLICATION_NAME
            if flags:
                credentials = tools.run_flow(flow, store, flags)
            else:  # Needed only for compatibility with Python 2.6
                credentials = tools.run(flow, store)
            print('Storing credentials to ' + credential_path)
        return credentials

    def get_spreadsheet_range(self, league, mode='driver'):
        cache_key = 'cache_{0}_{1}'.format(league, mode)
        range_name = '{0} Standings!{1}'.format(league, self.sheets_ranges[mode])

        if self.cache is None or cache_key not in self.cache:
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id, range=range_name).execute()
            values = result.get('values', [])
            if self.cache is not None:
                self.cache[cache_key] = values
        else:
            values = self.cache[cache_key]

        return values

    def get_spreadsheet_data(self):
        for league in self.leagues:
            self.leagues[league] = {
                'drivers': [],
                'teams': []
            }

            drivers = self.get_spreadsheet_range(league)
            for driver in drivers:
                self.leagues[league]['drivers'].append({
                    'position': int(driver[0]),
                    'name': driver[2],
                    'points': float(driver[3])
                })

            teams = self.get_spreadsheet_range(league, 'team')
            for team in teams:
                self.leagues[league]['teams'].append({
                    'position': int(team[0]),
                    'name': team[1],
                    'points': float(team[3])
                })

    def get_leaders(self):
        self.get_spreadsheet_data()
        results = {}

        for league in self.leagues:
            if league not in results:
                results[league] = {}

            results[league.upper()]['driver'] = [
                self.leagues[league]['drivers'][0]['name'],
                self.leagues[league]['drivers'][0]['points']
            ]
            results[league.upper()]['team'] = [
                self.leagues[league]['teams'][0]['name'],
                self.leagues[league]['teams'][0]['points']
            ]

        return results

    def find(self, name):
        self.get_spreadsheet_data()
        results = {}
        for league in self.leagues:
            if league not in results:
                results[league] = {
                    'drivers': [],
                    'teams': []
                }

            drivers = [result for result in self.leagues[league]['drivers'] if name.lower() in result['name'].lower()]
            if len(drivers) > 0:
                for driver in drivers:
                    results[league]['drivers'].append("{0} is {1} with {2} points".format(
                        driver['name'], ordinal(driver['position']), driver['points'])
                    )

            teams = [result for result in self.leagues[league]['teams'] if name.lower() in result['name'].lower()]
            if len(teams) > 0:
                for team in teams:
                    results[league]['teams'].append("{0} is {1} with {2} points".format(
                        team['name'], ordinal(team['position']), team['points'])
                    )

        return results

    def get_calendar(self, series):
        service = discovery.build('calendar', 'v3', http=self.http)
        cache_key = 'calendar_{0}'.format(series)

        if self.cache is None or cache_key not in self.cache:
            result = service.events().list(
                calendarId=self.calendar_ids[series],
                timeMin=self.now(), maxResults=25, singleEvents=True,
                orderBy='startTime').execute()
            events = result.get('items', [])
            if self.cache is not None:
                self.cache[cache_key] = events
        else:
            events = self.cache[cache_key]

        return events

    @staticmethod
    def now():
        return (datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) +
                timedelta(days=1)).isoformat() + 'Z'

    def format_race(self, event):
        start = event['start'].get('dateTime', event['start'].get('date'))
        start_date = event['start'].get('date')

        date_format = '%Y-%m-%d'
        delta = datetime.strptime(start_date, date_format) - datetime.strptime(self.now()[:10], date_format)

        return "{0} on {1} (about {2} days)".format(event['summary'], start, delta.days)

    def get_next_race(self, series='f1'):
        events = self.get_calendar(series)
        if not events:
            next_race = "No race found!"
            print('No upcoming events found.')
        else:
            next_race = self.format_race(events[0])

        return next_race

    def find_race(self, name, series='f1'):
        whenis = "No race found!"
        events = self.get_calendar(series)
        if not events:
            print('No events found.')
        else:
            results = [race for race in events if name.lower() in race['summary'].lower()]
            if len(results) > 0:
                whenis = self.format_race(results[0])

        return whenis

    def results_posted(self, league, round_number):
        data = self.get_spreadsheet_range(league, 'results')
        results = set([row[round_number + 2] for row in data])
        return not('-' in results and len(results) == 1)

    def results(self, league, round_number, return_count=0):
        results = []
        data = self.get_spreadsheet_range(league, 'results')
        for driver in data:
            try:
                if return_count == 0 or int(driver[round_number + 2]) in [n for n in range(1, return_count + 1)]:
                    results.append({
                        'name': driver[1],
                        'team': driver[0],
                        'position': driver[round_number + 2],
                        'current_points': driver[19]
                    })
            except ValueError:
                pass

        return sorted(results, key=lambda e: e['position'])

    def standings(self, league, round_number, mode='driver_standings'):
        results = []
        standings = self.get_spreadsheet_range(league, mode)
        for row in standings:
            if mode == 'driver_standings':
                try:
                    points = float(row[19])
                except ValueError:
                    points = 0

                results.append({
                    'name': row[1],
                    'team': row[0],
                    'points': float(points),
                    'positions': Counter(row[3:(3 + round_number)]),
                    'last_position': row[2 + round_number]
                })
            else:
                results.append({
                   'name': row[0],
                   'points': float(row[2])
                })

        return sorted(results, key=lambda e: e['points'], reverse=True)

    def leaderboard(self, league, round_number):
        leaderboard = {}
        standings = self.get_spreadsheet_range(league, 'results')
        for row in standings:
            name = row[1]
            leaderboard[name] = []

            this_round = {
                "points": [],
                "position": []
            }
            for tmp_round in row[3:round_number + 3]:
                try:
                    this_round['points'].append(calculate_points(int(tmp_round)))
                except ValueError:
                    this_round['points'].append(0)

            leaderboard[name].append(this_round)

        for r in range(round_number):
            print(r)

        # pprint(leaderboard)


if __name__ == '__main__':
    from cachetools import TTLCache

    ttlcache = TTLCache(maxsize=10, ttl=86400)
    req = GoogleRequests(ttlcache)

    # print(req.get_next_race('fsr'))
    # print(req.find_race('belgian', 'fsr'))
    # print(req.get_next_race())
    # print(req.find_race('belgian'))
    # print(req.get_leaders())
    # print(req.find('red'))

    # req.get_spreadsheet_data()
    # print(req.standings('2100', 'driver_standings'))
    # pprint(req.standings('1400', 5, 'driver_standings'))
    req.leaderboard('1700', 5)
