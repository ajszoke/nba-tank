"""
Author: Andrew Szoke (ajszoke)
Email: zoke2556@gmail.com
Created: Spring 2020

This script scrapes data from pro-football-reference.com to compile each team's running W-L record
as a function of each individual game. It outputs the results of each year into the 'data.json' file
located within this directory.
"""

import json
import logging
import urllib3
from bs4 import BeautifulSoup

# consts
START_YEAR = 1978  # first year in 82-game era
END_YEAR = 2020
NUM_GAMES_IN_A_SEASON = 16
OUTPUT_FILENAME_DETAIL = 'nfl-data.json'
OUTPUT_FILENAME_TOPLINE = 'nfl-avgLosingTeamGamesFrom500.csv'
URL_TEMPLATE = 'https://www.pro-football-reference.com/years/{year}/games.htm'

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
    winningTeam = tr.find(name="td", attrs={'data-stat': 'winner'}).find('a').get_text()
    losingTeam = tr.find(name="td", attrs={'data-stat': 'loser'}).find('a').get_text()
    isTie = tr.find(name="td", attrs={'data-stat': 'pts_win'}).get_text() == \
            tr.find(name="td", attrs={'data-stat': 'pts_lose'}).get_text()

    for team in [winningTeam, losingTeam]:
        # increment each team's game number
        teamGameNo = 1 if team not in teamGamesPlayed else teamGamesPlayed.get(team) + 1
        teamGamesPlayed[team] = teamGameNo

        if isTie:
            deltaWins = 0.5
        else:
            deltaWins = 1 if team == winningTeam else 0

        # initialize year-gameNum entry if needed
        if teamGameNo not in result[year]:
            result[year][teamGameNo] = {'totalGamesFrom500': 0}

        if teamGameNo != 1:
            teamWins = result[year][teamGameNo - 1][team].get('wins') + deltaWins
        else:
            teamWins = deltaWins

        teamDistFrom500 = teamWins - (teamGameNo / 2)
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
    seasonStr = str(year - 1) + '-' + str(year)

    thisUrl = URL_TEMPLATE.format(year=year)
    soup = make_soup(thisUrl)

    # iterate over game rows
    gameTable = soup.find(name='table', id='games').find('tbody')
    trs = gameTable.find_all('tr')
    for tr in trs:
        firstCell = tr.find(name='th', attrs={'class': 'right'})
        if firstCell is not None:
            firstCellVal = firstCell.get_text()
            try:
                int(firstCellVal)  # check if the cell is a week number
                process_game_row(tr, teamGamesPlayed, year)
            except ValueError:
                if firstCellVal != 'Week':
                    break  # start of playoffs

    # end-of-season calculations

    lastGameNo = 17  # default, may be overwritten below
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
