import praw
import prawcore
from praw.exceptions import APIException
import csv
from google import GoogleRequests
from datetime import datetime
import re
import utils
import inflect
import random
import json
import os
from itertools import filterfalse
import logging

# handler = logging.StreamHandler()
# handler.setLevel(logging.DEBUG)
# logger = logging.getLogger('prawcore')
# logger.setLevel(logging.DEBUG)
# logger.addHandler(handler)

DAYS_BEFORE_TIME_TRIAL = 7
DAYS_BEFORE_PRE_RACE = 3
DAYS_BEFORE_POST_RACE = 0


class TTBot:
    """ TimeTrialBot """

    def __init__(self):
        self.client = None
        self.subreddit = None
        self.bot_name = None
        self.drivers = {}

        self.schedule = {}
        self.load_schedule()
        self.load_drivers()

        self.positions = {
            '1': 'win', '2': '2nd place', '3': '3rd place', '4': '4th place', '5': '5th place', '6': '6th place',
            '7': '7th place', '8': '8th place', '9': '9th place', '10': '10th place', '11': '11th place',
            '12': '12th place', '13': '13th place', '14': '14th place', '15': '15th place', '16': '16th place',
            '17': '17th place', '18': '18th place', '19': '19th place', '20': '20th place', '21': '21st place',
            '22': '22nd place', '-': 'missed race', 'DSQ': 'disqualification', 'DNS': 'missed start',
            'Ret': 'retirement'
        }

        self.leagues = ['1400', '1700', '2100']
        self.google = GoogleRequests(None)

        # Number to retrieve when looking for time trial threads
        self.thread_count = 10

        logging.basicConfig(filename='ttbot.log', level=logging.INFO)

        utils.debug_log("Bot initialized")

    def load_schedule(self):
        # All dates are in UTC, check based on midnight of the current day
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # Load the schedule from disk
        with open('schedule.txt') as csvfile:
            schedule = csv.DictReader(csvfile, delimiter='|')
            for item in schedule:
                event_date = datetime.strptime(item['date'], '%Y-%m-%d')
                days_to_event = (event_date - today).days
                self.schedule[days_to_event] = {
                    'round': int(item['round']),
                    'race': item['race'],
                    'date': datetime.strftime(event_date, '%Y-%m-%d')
                }

    def run(self):
        self.connect_to_reddit()

        # Check for already created threads to see if they need updating
        threads = self.discover_time_trial_threads()
        if len(threads) > 0:
            self.process_time_trial_threads(threads)

        if DAYS_BEFORE_TIME_TRIAL in self.schedule:
            self.create_time_trial_thread()
        if DAYS_BEFORE_PRE_RACE in self.schedule:
            self.create_pre_race_thread()
        if DAYS_BEFORE_POST_RACE in self.schedule:
            self.create_post_race_thread()

    def connect_to_reddit(self):
        utils.debug_log("Setting up connection with Reddit")
        self.client = praw.Reddit('ttbot')
        self.subreddit = self.client.config.custom['subreddit']
        self.bot_name = self.client.config.custom['bot_name']
        utils.debug_log("Connected")

    def discover_time_trial_threads(self):
        threads = []
        subreddit = self.client.subreddit(self.subreddit)

        # Get the newest max_count posts.
        for submission in subreddit.new(limit=self.thread_count):
            # Check if the thread is a time trial thread
            if "[TT]" in submission.title:
                utils.debug_log("Found " + submission.url)
                threads.append(submission)

        utils.debug_log("Total " + str(len(threads)) + " threads found")

        # Return array of time trial threads
        return threads

    def process_time_trial_threads(self, threads):
        for thread in threads:
            # Wet and dry times tables need building
            old_times = utils.load_times(thread.title)
            times = []

            # Check if TTBot has replied with a table already, in which case it needs editing.
            already_replied = None

            # pattern = re.compile("^.*[^~{2}]\[((\d+)[{1}:|.](\d+)[{2}:|.](\d+))\].*?\((.*?)\).*$", re.IGNORECASE)
            pattern = re.compile(r"\[([\d:\.]+)\]\([^\)]*\)")

            # The amount of times submitted
            reply_count = 0

            for top_reply in thread.comments:
                reply_count += 1

                if str(top_reply.author) == self.bot_name and "# Time Trial Standings:" in top_reply.body:
                    # We have found a results table already, keep a hold of that reply.
                    utils.debug_log("Bot already posted a table.")
                    already_replied = top_reply

            for top_reply in thread.comments:
                if str(top_reply.author) != self.bot_name:

                    reply = top_reply.body.split("\n")
                    for line in reply:
                        result = pattern.findall(line)

                        if len(result) > 0:
                            author = str(top_reply.author)
                            thing = top_reply.name

                            # Find the lowest time
                            best_time = min([utils.convert_time(t) for t in result])
                            times.append({'name': author, 'time': best_time, 'thing': thing})

            utils.debug_log(str(reply_count) + " replies found")

            replytext = "# Time Trial Standings:"

            # Build the tables based on the dry and wet arrays
            if len(times) > 0:
                replytext += self.build_table(times)
                utils.save_times(thread.title, times)

            footer = "\n[Feedback | Bugs](http://www.reddit.com/message/compose/?to={})".format(self.bot_name)

            # Submit reply.
            try:
                if old_times != times:
                    if already_replied is not None:
                        utils.debug_log("Already replied... editing")
                        already_replied.edit(replytext + footer)
                        already_replied.mod.distinguish('yes', sticky=True)
                        utils.debug_log("Edited post")
                    else:
                        utils.debug_log("Adding new reply")
                        comment = thread.reply(replytext + footer)
                        comment.mod.distinguish('yes', sticky=True)
                        utils.debug_log("Added new reply")
                else:
                    utils.debug_log("Times haven't changed, not posting")
            except APIException:
                utils.debug_log("API Exception raised, unable to post to thread")

    def build_table(self, times):
        table = utils.adjust_table(times, sort_by='time', reverse=False, is_float=True)
        if len(table) > 0:
            replytext = ""
            replytext += ("\n\n|Q|Driver|League|Time|Diff.|Rel. Diff.|Points\n"
                          "|:-:|-|:-:|-|-:|-:|:-:\n")

            for row in sorted(table, key=lambda item: item['position']):
                time = utils.format_time(row['time'])

                try:
                    driver = utils.find_driver(row['name'], self.drivers)
                    league = ', '.join((driver['leagues']))
                except StopIteration:
                    utils.debug_log("League not found for '{0}'".format(row['name']))
                    league = ""

                # Building the table row in Reddit's MarkDown.
                replytext = replytext + ("|" + str(row['position'])
                                         + "|" + row['name'] + "|"
                                         + league + "|"
                                         + "[" + time + "](#thing_" + row['thing'] + ")|")

                # Add difference to the table
                replytext = replytext + str(row['diff']) + "|"

                # Add relative difference to the table
                replytext = replytext + str(row['relative_diff']) + "|"

                # Add points
                replytext = replytext + str(utils.calculate_points(row['position']))

                # Add the new line
                replytext = replytext + "\n"

            return replytext

    def load_drivers(self):
        with open('drivers.json', 'r') as f:
            self.drivers = json.load(f)

    def create_time_trial_thread(self):
        schedule = self.schedule[DAYS_BEFORE_TIME_TRIAL]

        post_title = "[TT] Round {round} - {race}".format(
            round=schedule['round'],
            race=schedule['race']
        )
        ttcount = 0
        subreddit = self.client.subreddit(self.subreddit)
        for submission in subreddit.new(limit=self.thread_count):
            # If there is already a time trial thread about the upcoming event.
            if post_title == submission.title:
                ttcount += 1

        if ttcount == 0:
            utils.debug_log("{race} TT thread needed".format(race=schedule['race']))

            with open('time-trial-body.txt') as f:
                post_body = f.read().format(round=schedule['round'], race=schedule['race'])

            utils.create_thread(subreddit, post_title, post_body)
        else:
            utils.debug_log("TT thread already made for {race}".format(race=schedule['race']))

    def create_pre_race_thread(self):
        schedule = self.schedule[DAYS_BEFORE_PRE_RACE]

        post_title = "[S9R{round}] {race} pre-race thread".format(round=schedule['round'], race=schedule['race'])
        prcount = 0
        subreddit = self.client.subreddit(self.subreddit)
        for submission in subreddit.new(limit=10):
            # If there is already a pre-race thread about the upcoming event.
            if post_title == submission.title:
                prcount += 1

        if prcount == 0:
            utils.debug_log("{race} pre-race thread needed".format(race=schedule['race']))

            table_1400 = self.post_race_details('1400', int(schedule['round']))
            table_1700 = self.post_race_details('1700', int(schedule['round']))
            table_2100 = self.post_race_details('2100', int(schedule['round']))

            with open('pre-race-body.txt') as f:
                post_body = f.read().format(
                    round=schedule['round'],
                    race=schedule['race'],
                    date=schedule['date'],
                    table_1400=table_1400['standings'],
                    table_1700=table_1700['standings'],
                    table_2100=table_2100['standings'],
                )

            utils.create_thread(subreddit, post_title, post_body)
        else:
            utils.debug_log("No pre-race thread needed today")

    def create_post_race_thread(self):
        schedule = self.schedule[DAYS_BEFORE_POST_RACE]
        for league in self.leagues:
            if self.google.results_posted(league, int(schedule['round'])):
                post_title = '[{league}] S9R{round} - {race} - Post-Race Thread'.format(
                    league=league,
                    round=schedule['round'],
                    race=schedule['race']
                )

                date = datetime.strptime(schedule['date'], '%Y-%m-%d')

                prcount = 0
                subreddit = self.client.subreddit(self.subreddit)
                for submission in subreddit.new(limit=self.thread_count):
                    if post_title == submission.title:
                        prcount += 1

                if prcount == 0:
                    utils.debug_log("{race} post-race thread needed for {league}".format(
                        race=schedule['race'], league=league
                    ))

                    details = self.post_race_details(league, int(schedule['round']))

                    with open('post-race-body.txt') as f:
                        post_body = f.read().format(
                            round=schedule['round'],
                            race=schedule['race'],
                            date=date.strftime('%B %d, %Y'),
                            results=details['results'],
                            standings=details['standings'],
                            highlights=details['highlights']
                        )

                    utils.create_thread(subreddit, post_title, post_body)

                    self.update_sidebar()
                    self.update_banner()
            else:
                utils.debug_log("Results not yet posted for {league}".format(league=league))

    def post_race_details(self, league, round_number):
        engine = inflect.engine()
        highlights = {}

        standings = {}
        results = {}

        standings['driver'] = self.google.standings(league, round_number)
        standings['team'] = self.google.standings(league, round_number, 'team_standings')

        results['driver'] = self.google.results(league, round_number, 10)
        for row in results['driver']:
            row['points'] = utils.calculate_points(int(row['position']))

        content = {
            'standings': utils.build_standings_table(standings),
            'results': utils.build_standings_table(results)
        }

        # filter out the drivers that haven't participated at all
        standings = filterfalse(lambda x: len(x['positions'].keys()) == 1 and list(x['positions'].keys())[0] == '-',
                                standings['driver'])
        for entry in standings:
            last_position_count = entry['positions'][entry['last_position']]
            last_position = "{} {}".format(
                engine.number_to_words(engine.ordinal(last_position_count)),
                self.positions.get(entry['last_position'])
            )

            if entry['name'] != 'Open' and entry['name'] != '':
                highlights[entry['name']] = last_position

        random_highlights = []
        for num in range(0, 5):
            entry = random.choice(list(highlights.keys()))
            if entry != '' and entry != 'Open':
                random_highlights.append(
                    "* {} for {}".format(highlights[entry], entry)
                )
                del highlights[entry]

        content['highlights'] = '\n'.join(random_highlights)

        return content

    def update_sidebar(self):
        position_template = "{league} | [](/mini-flair-{team} \"\")[](/flag-{country} \"\") {driver} | {points} |"
        schedule_template = "{date} | [](/flag-{flag} \"{country}\") {country} |"

        leaders = self.google.get_leaders()
        leader_text = {}
        for league in leaders:
            try:
                driver_name = leaders[league]['driver'][0]
                driver_points = leaders[league]['driver'][1]
                driver = utils.find_driver(driver_name, self.drivers)

                leader_text[league] = position_template.format(
                    league=league,
                    team=driver['leagues'][league],
                    country=driver['country'],
                    driver=driver_name,
                    points=utils.format_float(driver_points)
                )
            except StopIteration:
                utils.debug_log("Driver not found")
                leader_text[league] = ''

        filtered = sorted(filter(lambda x: int(x) >= 0, self.schedule))[:4]
        next_races = []
        for race in filtered:
            flag = utils.country_to_flag(self.schedule[race]['race'])
            date = datetime.strptime(self.schedule[race]['date'], '%Y-%m-%d')
            next_races.append(schedule_template.format(
                date=date.strftime('%d %b'),
                flag=flag,
                country=self.schedule[race]['race']
            ))

        with open('sidebar.txt') as f:
            sidebar_body = f.read().format(
                league_1400=leader_text['1400'],
                league_1700=leader_text['1700'],
                league_2100=leader_text['2100'],
                schedule='\n'.join(next_races),
            )

        self.client.subreddit(self.subreddit).mod.update(description=sidebar_body)
        utils.debug_log('Sidebar updated')

    def update_banner(self):
        next_race = self.schedule[sorted(filter(lambda x: int(x) >= 0, self.schedule))[0]]
        filename = "banners/{race}.jpg".format(race=next_race['race'].lower())
        if not os.path.exists(filename):
            filename = "banners/{race}.png".format(race=next_race['race'].lower())

        try:
            ss = self.client.subreddit(self.subreddit).stylesheet
            ss.upload('banner', filename)
            stylesheet = self.client.subreddit(self.subreddit).stylesheet().stylesheet
            ss.update(stylesheet)
            utils.debug_log('Banner updated')
        except FileNotFoundError:
            utils.debug_log('Banner file not found')
        except APIException:
            utils.debug_log('API exception thrown')
        except prawcore.TooLarge:
            utils.debug_log('Banner image is too large')


# End of class, start program

bot = TTBot()
bot.run()
# bot.connect_to_reddit()
# bot.update_sidebar()
