"""
Author: Andrew Szoke (ajszoke)
Email: zoke2556@gmail.com
Created: Spring 2020

This script scrapes data from basketball-reference.com to compile each team's running W-L record as
a function of each individual game. It outputs the results of each year into the 'data.json' file
located within this directory.
"""

import json
import logging
import urllib3
from bs4 import BeautifulSoup

# consts
START_YEAR = 1968  # first year in 82-game era
END_YEAR = 2020
NUM_GAMES_IN_A_SEASON = 16
OUTPUT_FILENAME_DETAIL = 'data.json'
OUTPUT_FILENAME_TOPLINE = 'avgLosingTeamGamesFrom500.csv'
URL_TEMPLATE = 'https://www.basketball-reference.com/leagues/NBA_{year}_games-{month}.html'
months = ['september', 'october', 'november', 'december', 'january', 'february', 'march', 'april', 'may', 'june']

# logging
LOG_FORMAT = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('local')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(LOG_FORMAT)
logger.addHandler(ch)

# globals
result = {}
avgLosingTeamGamesFrom500 = []
losingTeamsSqDistFrom500 = []
tankIndex = []
tankSquaredIndex = []
shortSeasons = {}

uniqueTeams = set()


def make_soup(url):
    http = urllib3.PoolManager()
    r = http.request('GET', url)
    return BeautifulSoup(r.data, 'lxml')


def process_game_row(tr, teamGamesPlayed, year):
    vizTeam = tr.find(name="td", attrs={'data-stat': 'visitor_team_name'}).find('a').get_text()
    vizPts = int(tr.find(name="td", attrs={'data-stat': 'visitor_pts'}).get_text())

    homeTeam = tr.find(name="td", attrs={'data-stat': 'home_team_name'}).find('a').get_text()
    homePts = int(tr.find(name="td", attrs={'data-stat': 'home_pts'}).get_text())

    # n.b.: nba games cannot end in a tie
    winningTeam = vizTeam if vizPts > homePts else homeTeam
    losingTeam = vizTeam if vizPts < homePts else homeTeam

    for team in [winningTeam, losingTeam]:
        # increment each team's game number
        teamGameNo = 1 if team not in teamGamesPlayed else teamGamesPlayed.get(team) + 1
        teamGamesPlayed[team] = teamGameNo

        # initialize year-gameNum entry if needed
        if teamGameNo not in result[year]:
            result[year][teamGameNo] = {'totalGamesFrom500': 0}

        if teamGameNo != 1:
            teamWins = result[year][teamGameNo - 1][team].get('wins')
            if team == winningTeam:
                teamWins += 1
            teamLosses = teamGameNo - teamWins
        else:
            teamWins = 1 if team == winningTeam else 0
            teamLosses = 0 if team == winningTeam else 1

        teamDistFrom500 = teamWins - teamLosses
        if teamDistFrom500 > 0:
            recordKind = 'winning'
        elif teamDistFrom500 < 0:
            recordKind = 'losing'
        else:
            recordKind = '500'

        # add team's entry to this game in this year
        teamAbsDistFrom500 = abs(teamDistFrom500)
        result[year][teamGameNo][team] = {
            'wins': teamWins,
            'distFrom500': teamAbsDistFrom500,
            'recordKind': recordKind
        }

        # calc change to overall year dist from 500
        result[year][teamGameNo]['totalGamesFrom500'] = result[year][teamGameNo]['totalGamesFrom500'] \
                                                        + teamAbsDistFrom500

        uniqueTeams.add(team)


for year in range(START_YEAR, END_YEAR + 1):
    result[year] = {}
    teamGamesPlayed = {}
    yearComplete = False
    seasonStr = str(year - 1) + '-' + str(year)

    for month in months:

        # malformed page as of 4/11/20; no games
        if month == 'september' and year == 2019:
            continue

        # no marked end of regular season for certain years
        if month == 'april' and year in [1980, 2020]:
            break

        thisUrl = URL_TEMPLATE.format(year=year, month=month)
        soup = make_soup(thisUrl)

        # check if month contains games played
        noGamesPlayed = soup.find(name='h1', text='Page Not Found (404 error)') is not None
        if noGamesPlayed:
            logYear = str(year)
            if month in ['september', 'october', 'november', 'december']:
                logYear = str(year - 1)
            logger.info('No game data for ' + month + ' ' + logYear)
            continue

        # try to find playoffs divider
        postseasonLine = soup.find(name='th', text='Playoffs')
        if postseasonLine is not None:
            postseasonLine = postseasonLine.find_parent('tr')

        # iterate over game rows
        gameTable = soup.find(name='table', id='schedule').find('tbody')
        trs = gameTable.find_all('tr')
        for tr in trs:
            if tr is not postseasonLine:
                process_game_row(tr, teamGamesPlayed, year)
            else:
                yearComplete = True
                break

        if yearComplete:
            break

    # end-of-season calculations

    lastGameNo = 82  # default, may be overwritten below
    if year == 2020:
        lastGameNo = 63  # last game with all 30 teams
        shortSeasons[year] = lastGameNo
    for gameNo in range(1, lastGameNo + 1):
        # calculate the avg dist from 500
        try:
            gameNoEntry = result[year][gameNo]
            numTeams = len(gameNoEntry) - 1  # every key is a team except the 'totalGamesFrom500' key
            gameNoEntry['avgGamesFrom500'] = gameNoEntry['totalGamesFrom500'] / numTeams
        except KeyError:
            lastGameNo = gameNo - 1
            logger.warning(seasonStr + ' season ends at game ' + str(lastGameNo))
            shortSeasons[year] = lastGameNo
            break

    # calculate the year's "tankiness"
    totalLosingTeamGamesFrom500 = 0
    yearEntry = result[year]
    lastGameEntryCopy = yearEntry[lastGameNo].copy()
    del lastGameEntryCopy['totalGamesFrom500']  # just want the teams here
    del lastGameEntryCopy['avgGamesFrom500']  # just want the teams here
    numTeamsInNba = len(lastGameEntryCopy)
    losingTeams = {k: v for k, v in lastGameEntryCopy.items() if v['recordKind'] == 'losing'}
    numLosingTeams = len(losingTeams)
    pctLosingTeams = numLosingTeams / numTeamsInNba
    for teamData in losingTeams.values():
        teamDistFrom500 = teamData['distFrom500']
        totalLosingTeamGamesFrom500 += teamDistFrom500
    yearEntry['numLosingTeams'] = numLosingTeams

    avgLosingTeamGamesFrom500Val = round(totalLosingTeamGamesFrom500 / numLosingTeams, 3)
    avgLosingTeamGamesFrom500.append([year, avgLosingTeamGamesFrom500Val])
    yearEntry['avgLosingTeamGamesFrom500'] = avgLosingTeamGamesFrom500Val

    logger.info('Finished ' + seasonStr)

with open(OUTPUT_FILENAME_DETAIL, 'w') as f:
    json.dump(result, f)
    logger.info('Created ' + OUTPUT_FILENAME_DETAIL)

with open(OUTPUT_FILENAME_TOPLINE, 'w') as f:
    avgLosingTeamGamesFrom500Str = "Year,RealOrProjGamesAbove500,RealGamesAbove500IfShortSeason\n"

    for elem in avgLosingTeamGamesFrom500:
        thisYear = elem[0]
        realOrProjGamesAbove500 = None
        realGamesAbove500IfShortSeason = None

        if thisYear not in shortSeasons.keys():
            realOrProjGamesAbove500 = elem[1]
            realGamesAbove500IfShortSeason = ''
        else:
            realGamesAbove500 = elem[1]
            realOrProjGamesAbove500 = str((NUM_GAMES_IN_A_SEASON / shortSeasons[thisYear]) * realGamesAbove500)
            realGamesAbove500IfShortSeason = str(realGamesAbove500)

        avgLosingTeamGamesFrom500Str = avgLosingTeamGamesFrom500Str + str(thisYear) + ',' \
                                       + str(realOrProjGamesAbove500) + ',' + realGamesAbove500IfShortSeason + '\n'

    f.write(avgLosingTeamGamesFrom500Str)
    logger.info('Created ' + OUTPUT_FILENAME_TOPLINE)
