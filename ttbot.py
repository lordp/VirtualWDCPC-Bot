import praw
from praw.exceptions import APIException
import csv
from google import GoogleRequests
from datetime import datetime
import re
import utils
import inflect
import random
import json
from pprint import pprint

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

        # logging.basicConfig(filename='ttbot.log', level=logging.INFO)

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
        elif DAYS_BEFORE_PRE_RACE in self.schedule:
            self.create_pre_race_thread()
        elif DAYS_BEFORE_POST_RACE in self.schedule:
            self.create_post_race_thread()

    def connect_to_reddit(self):
        utils.debug_log("Setting up connection with Reddit")
        self.client = praw.Reddit('ttbot-test')
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
        # Load the drivers from the league text files into array
        self.load_drivers()

        for thread in threads:
            # Wet and dry times tables need building
            times = []

            # Check if TTBot has replied with a table already, in which case it needs editing.
            already_replied = 0

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

            footer = "\n[Feedback | Bugs](http://www.reddit.com/message/compose/?to={})".format(self.bot_name)

            # Submit reply.
            try:
                if already_replied != 0:
                    utils.debug_log("Already replied... editing")
                    already_replied.edit(replytext + footer)
                    already_replied.mod.distinguish('yes', sticky=True)
                    utils.debug_log("Edited post")
                else:
                    if len(times) > 0:
                        utils.debug_log("Adding new reply")
                        comment = thread.reply(replytext + footer)
                        comment.mod.distinguish('yes', sticky=True)
                        utils.debug_log("Added new reply")
                    else:
                        utils.debug_log("No replies, so no table posted")
            except APIException:
                utils.debug_log("API Exception raised, unable to post to thread")

    def build_table(self, times):
        table = utils.adjust_table(times, sort_by='time', reverse=False, is_float=True)
        if len(table) > 0:
            replytext = ""
            replytext += ("\n\n|Q|Driver|League|Time|Diff.|Rel. Diff.|Points\n"
                          "|:-:|-|:-:|-|-:|-:|:-:\n")

            for row in table:
                time = utils.format_time(row['time'])

                try:
                    driver = next(item for item in self.drivers if item["name"] == row['name'])
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
            utils.debug_log("TT thread already made")

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

            table_1400 = self.post_race_details('1400', schedule['round'])
            table_1700 = self.post_race_details('1700', schedule['round'])
            table_2100 = self.post_race_details('2100', schedule['round'])

            with open('pre-race-body.txt') as f:
                post_body = f.read().format(
                    round=schedule['round'],
                    race=schedule['race'],
                    date=schedule['date'],
                    table_1400_driver=table_1400['driver'],
                    table_1400_team=table_1400['team'],
                    table_1700_driver=table_1700['driver'],
                    table_1700_team=table_1700['team'],
                    table_2100_driver=table_2100['driver'],
                    table_2100_team=table_2100['team']
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
                            driver_standings=details['driver'],
                            team_standings=details['team'],
                            highlights=details['highlights']
                        )

                    utils.create_thread(subreddit, post_title, post_body)
            else:
                utils.debug_log("Results not yet posted for {league}".format(league=league))

    def post_race_details(self, league, round_number):
        engine = inflect.engine()
        highlights = {}

        driver = self.google.standings(league, round_number)
        team = self.google.standings(league, round_number, 'team_standings')

        results = self.google.results(league, round_number, 5)
        for row in results:
            row['points'] = utils.calculate_points(int(row['position']))

        content = {
            'driver': utils.build_standings_table('driver', driver),
            'team': utils.build_standings_table('team', team),
            'results': utils.build_standings_table('driver', results)
        }

        for entry in driver:
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
        template = "{league} | [](/mini-flair-{team} \"\")[](/flag-{country} \"\") {driver} | {points} |"

        leaders = self.google.get_leaders()
        leader_text = {}
        for league in leaders:
            try:
                driver_name = leaders[league]['driver'][0]
                driver_points = leaders[league]['driver'][1]
                driver = next((item for item in self.drivers if item["name"] == driver_name), False)

                leader_text[league] = template.format(
                    league=league,
                    team=driver['leagues'][league],
                    country=driver['country'],
                    driver=driver_name,
                    points=utils.format_float(driver_points)
                )
            except TypeError:
                leader_text[league] = ''

        with open('sidebar.txt') as f:
            sidebar_body = f.read().format(
                league_1400=leader_text['1400'],
                league_1700=leader_text['1700'],
                league_2100=leader_text['2100'],
            )

        self.client.subreddit(self.subreddit).mod.update(description=sidebar_body)


# End of class, start program

bot = TTBot()
bot.run()
# bot.connect_to_reddit()
# bot.update_sidebar()