#!/usr/bin/env python2

## Slack Integration / Web API for tracking statistics for Foosball games among players in our organization.
## Created:  June, 2015
## Created by:  shockema@gmail.com
## Copyright 2015, Stephen Hockema

import datetime
import re
import MySQLdb
import requests
import json
import random
from collections import defaultdict
from flask import Flask
from flask import request, abort
from flask.json import jsonify
import logging
from logging import Formatter
from logging import FileHandler


app = Flask(__name__)


_g_config = {}
_g_configFile = "./foosball.cfg"     ## Adjust to environment...



def _readConfigFile():
    global _g_configFile
    global _g_config
    try:
        with open(_g_configFile) as inpf:        
            _g_config = json.load(inpf)    
    except Exception as e:
        app.logger.error("Caught exception reading the config file '" + _g_configFile + "':  " + str(e))
        abort(500) 
    if ("logging" not in _g_config  or  "database" not in _g_config  or  "slack" not in _g_config):
        app.logger.error("Config file '" + _g_configFile + "' missing required section.")
        abort(500)


def _enableLogging():
    global _g_config
    if (("started" in _g_config["logging"]  and  _g_config["logging"]["started"])  or  app.debug):
        return
    handler = FileHandler(_g_config["logging"]["logfile"])
    handler.setFormatter(Formatter('%(asctime)s %(levelname)s line=%(lineno)d - %(message)s'))
    handler.setLevel(_g_config["logging"]["level"])
    app.logger.addHandler(handler)
    _g_config["logging"]["started"] = True


def _startup():
    _readConfigFile()
    _enableLogging()


def _connectDB():
    global _g_config
    if ("optionalSocket" in _g_config["database"]):
        return MySQLdb.connect(_g_config["database"]["server"], \
                               _g_config["database"]["user"], \
                               _g_config["database"]["password"], \
                               _g_config["database"]["name"], \
                               unix_socket=_g_config["database"]["optionalSocket"])
    else:
        return MySQLdb.connect(_g_config["database"]["server"], \
                               _g_config["database"]["user"], \
                               _g_config["database"]["password"], \
                               _g_config["database"]["name"])


def _multiDict(n, type):
    if (n <= 1):
        return type()
    return defaultdict(lambda:_multiDict(n - 1, type))

def _incrElement(dictref, key, amount = 1):
    if (key not in dictref):
        dictref[key] = 0
    dictref[key] = dictref[key] + amount


class PlayerStats(object):
    def __init__(self, name):
        self.name = name
        self.reset()

    def reset(self):
        self.gamesPlayed = _multiDict(3, int)              # {rel, rval}
        self.gameResults = _multiDict(4, int)              # {result, rel, rval}
        self.goalDelta = _multiDict(3, int)                # {rel, rval}

    def sortKey(self, rel, rval):
        return (float(self.gameResults["win"][rel][rval]) / self.gamesPlayed[rel][rval]) if (self.gamesPlayed[rel][rval] > 0) else 0.0

    def tally(self, colorAs, colorAgainst, db):
        query = "SELECT G." + colorAs + "Score, G." + colorAgainst + "Score, G." + colorAs + "Offense, G." + colorAs + "Defense, G." + colorAgainst + "Offense, G." + colorAgainst + "Defense, P.id "
        query += "FROM Game AS G, Player AS P WHERE P.name = '" + self.name + "' AND (P.id = G." + colorAs + "Offense  OR  P.id = G." + colorAs + "Defense)"
        cursor = db.cursor()
        try:
            cursor.execute(query)
            for row in cursor.fetchall():
                goalDelta = row[0] - row[1]
                if (row[0] > row[1]):
                    result = "win"
                elif (row[0] < row[1]):
                    result = "loss"
                else:
                    result = "tie"
                _incrElement(self.gamesPlayed[""], "")
                _incrElement(self.gameResults[result][""], "")
                _incrElement(self.goalDelta[""], "", goalDelta)
                _incrElement(self.gamesPlayed["as"], colorAs)
                _incrElement(self.gameResults[result]["as"], colorAs)
                _incrElement(self.goalDelta["as"], colorAs, goalDelta)
                if (row[2] == row[3]):
                    _incrElement(self.gamesPlayed["with"], "")
                    _incrElement(self.gameResults[result]["with"], "")
                    _incrElement(self.goalDelta["with"], "", goalDelta)
                else:
                    partner = str(row[2]) if (row[3] == row[6]) else str(row[3])
                    _incrElement(self.gamesPlayed["with"], partner)
                    _incrElement(self.gameResults[result]["with"], partner)
                    _incrElement(self.goalDelta["with"], partner, goalDelta)
                if (row[4] == row[5]):
                    opponent = str(row[2]) if (row[4] == row[6]) else str(row[4])
                    _incrElement(self.gamesPlayed["against"], opponent)
                    _incrElement(self.gameResults[result]["against"], opponent)
                    _incrElement(self.goalDelta["against"], opponent, goalDelta)
                else:
                    opp1 = str(row[1]) if (row[4] == row[6]  or  row[5] == row[6]) else str(row[4])
                    opp2 = str(row[2]) if (row[4] == row[6]  or  row[5] == row[6]) else str(row[5])
                    opponent = opp1 + "+" + opp2
                    _incrElement(self.gamesPlayed["against"], opponent)
                    _incrElement(self.gameResults[result]["against"], opponent)
                    _incrElement(self.goalDelta["against"], opponent, goalDelta)
        except Exception as e:
            app.logger.error("Caught exception tallying player stats for '" + self.name + "' as '" + colorAs + "' against '" + colorAgainst + "':  " + str(e))

    @staticmethod
    def categoryString(rel, rval):
        if (rel == ""  and  rval == ""):
            return "overall"
        elif (rel == "with"  and  rval == ""):
            return "solo"
        elif (rel == "as"):
            return rel + " " + rval
        else:
            return rel

    def typeToDictionary(self, rel, rval):
        return { "category" : PlayerStats.categoryString(rel, rval), \
                 "categoryStats" : { \
                     "gamesPlayed" : self.gamesPlayed[rel][rval], \
                     "wins" : self.gameResults["win"][rel][rval], \
                     "losses" : self.gameResults["loss"][rel][rval], \
                     "ties" : self.gameResults["tie"][rel][rval], \
                     "goalDifferential" : self.goalDelta[rel][rval] } }

    def toDictionary(self):
        resultArr = []
        for rel in self.gamesPlayed:
            if (rel != "against"):
                for rval in self.gamesPlayed[rel]:
                    if (rel != "with"  or  len(rval) == 0):
                        resultArr.append(self.typeToDictionary(rel, rval))
        return { "player" : self.name, "stats" : resultArr }

    @staticmethod
    def header(cat = "", separator = "   "):
        result = ""
        space = " " if (len(cat) > 0) else ""
        for outcome in ("wins", "losses", "ties"):
            result += separator + cat + space + outcome
        result += separator + cat + space + "win%"
        result += separator + cat + space + "GD"
        result += "\n"
        return result

    ## TODO:  format better here...
    def typeToString(self, rel, rval, showName = False, showZeros = True, showHeader = True, separator = "\t"):
        result = ""
        if (showHeader):
            result = PlayerStats.header(PlayerStats.categoryString(rel, rval))
        if (not showZeros  and  self.gamesPlayed[rel][rval] == 0):
            return result
        result += (self.name + ":") if (showName) else "\t"   # header() starts with tab for this
        for outcome in ("win", "loss", "tie"):
            result += separator + str(self.gameResults[outcome][rel][rval])
        if (self.gamesPlayed[rel][rval] != 0):
            result += separator + "%4.1f" % ((100.0 * self.gameResults["win"][rel][rval]) / self.gamesPlayed[rel][rval])
        else:
            result += separator + "---"
        result += separator + str(self.goalDelta[rel][rval])
        result += "\n"
        return result



def _postSlackMessage(msg):
    global _g_config
    apiURL = "https://slack.com/api/chat.postMessage"
    r = requests.post(apiURL, data={ 'token' : _g_config["slack"]["apiToken"], \
                                     'channel' : _g_config["slack"]["channel"], \
                                     'username' : _g_config["slack"]["postAsUser"], \
                                     'text' : msg + "\n"})
    if (r.status_code >= 300):
        app.logger.warning("Posting to slack failed:  " + r.text)


def _postInsult(db, winnerId, loserId, losingColor):
    loser = _playerIdToName(db, loserId)
    if (loser == "steve"):
        return False
    try:
        lines = []
        for line in open(_g_config["insultFile"]):
            lines.append(line)
        if (len(lines) > 0):
            insult = lines[random.randint(0, len(lines) - 1)].replace("<loser/>", loser).replace("<winner/>", _playerIdToName(db, winnerId)).replace("<losingColor/>", losingColor)
            _postSlackMessage(insult + "\n")
    except Exception as e:
        return False
    return True


def _isAscii(s):
    return all(ord(c) < 128 for c in s)

def _sqlOk(s):
    return (_isAscii(s)  and  "'" not in s)


def _checkPlayer(db, playerName):
    if (not _sqlOk(playerName)):
        abort(401)
    cursor = db.cursor()
    try:
        cursor.execute("SELECT * FROM Player WHERE name = '" + str(playerName) + "'")
        hitname = cursor.fetchone()
        if (hitname is not None  and  len(hitname) > 0):
            return True
    except Exception as e:
        app.logger.error(" Caught exception in _checkPlayer for '" + str(playerName) + "':  " + str(e))
    return False


def _playerId(db, playerName):
    if (not _sqlOk(playerName)):
        abort(401)
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id FROM Player WHERE name = '" + str(playerName) + "'")
        hitname = cursor.fetchone()
        if (hitname is not None  and  len(hitname) > 0):
            return int(hitname[0])
    except Exception as e:
        app.logger.error("Caught exception in _playerId for '" + str(playerName) + "':  " + str(e))
    return -1


def _playerIdToName(db, playerId):
    cursor = db.cursor()
    try:
        cursor.execute("SELECT name FROM Player WHERE id = " + str(playerId))
        hitname = cursor.fetchone()
        if (hitname is not None  and  len(hitname) > 0):
            return hitname[0]
    except Exception as e:
        app.logger.error("Caught exception in _playerIdToName for '" + str(playerId) + "':  " + str(e))
    return "Unknown"


def _addCommandArgsFromFlaskRequest(params, commandArgs):
    if (request.method == "POST"):
        for param in params:
            if (param not in request.form):
                return False
        for param in params:
            commandArgs.append(request.form[param])
    else:
        for param in params:
            if (param not in request.args):
                return False
        for param in params:
            commandArgs.append(request.args.get(param))
    return True



##################
## API Handlers ##
##################

def _newPlayer(commandArgs, db, user):
    if (len(commandArgs) != 2):
        return "newPlayer command requires one argument.  Use \"/foosball help\"."
    playerName = commandArgs[1]
    if (len(playerName) > 256):
        abort(401)
    if (_checkPlayer(db, playerName)):
        return "User already exists." 
    sql = "INSERT INTO Player (name) VALUES ('" + str(playerName) + "')"
    cursor = db.cursor()
    try:
        cursor.execute(sql)
        db.commit()
    except Exception as e:
        db.rollback()
        app.logger.error("Caught exception trying to add new player ('" + str(playerName) + "'):  " + str(e))
        return "Adding player failed."
    _postSlackMessage(user + " added new player:  " + playerName)
    return "Added player "+ playerName + "."


def _changePlayer(commandArgs, db, user):
    if (len(commandArgs) != 3):
        return "changePlayer command requires two argument.  Use \"/foosball help\"."
    playerName = commandArgs[1]
    targetName = commandArgs[2]
    if (len(targetName) > 256):
        abort(401)
    if (_checkPlayer(db, targetName)):
        return "User already exists." 
    currentId = _playerId(db, playerName)
    if (-1 == currentId):
        return "User not found." 
    sql = "UPDATE Player SET name='" + targetName + "' WHERE id=" + str(currentId)
    cursor = db.cursor()
    try:
        cursor.execute(sql)
        db.commit()
    except Exception as e:
        db.rollback()
        app.logger.error("Caught exception trying to change player name from '" + str(playerName) + "' to '" + str(targetName) + "':  " + str(e))
        return "Changing player name failed."
    _postSlackMessage(user + " changed player name '" + playerName + "' to '" + targetName + "'.")
    return "Changed player '" + playerName + "' to '" + targetName + "'."


def _getPlayers(commandArgs, db, user):
    if (len(commandArgs) != 1):
        return "players comand requires no arguments.  Use \"/foosball help\"."
    players = []
    cursor = db.cursor()
    try:
        cursor.execute("SELECT name FROM Player")
        for row in cursor.fetchall():
            players.append(str(row[0]))
    except Exception as e:
        app.logger.error("Caught exception trying to retrieve all user names:  " + str(e))
        return "Error!"
    return jsonify({ "players" : players })


def _stats(commandArgs, db, user, client = "slack"):
    if (len(commandArgs) > 3):
        return "stats comand takes at most two arguments.  Use \"/foosball help\"."
    elif (len(commandArgs) == 1):
        stats = []
        cursor = db.cursor()
        try:
            cursor.execute("SELECT name FROM Player")
            for row in cursor.fetchall():
                stats.append(PlayerStats(row[0]))
        except Exception as e:
            app.logger.error("Caught exception trying to retrieve all user names:  " + str(e))
            return "Error!"
        if (len(stats) == 0):
            return "no games."
        for ps in stats:
            ps.tally('red', 'black', db)
            ps.tally('black', 'red', db)
        if (client == "slack"):
            result = ""
            for cat in (("", ""), ("with", ""), ("as", "red"), ("as", "black")):
                result += PlayerStats.header(PlayerStats.categoryString(cat[0], cat[1]))
                stats.sort(key=lambda pse: pse.sortKey(cat[0], cat[1]), reverse=True)
                for ps in stats:
                    result += ps.typeToString(cat[0], cat[1], True, False, False)
                result += "\n"
            return result
        else:
            resultArr = []
            for ps in stats:
                resultArr.append(ps.toDictionary())
            return jsonify({ "allStats" : resultArr })
    elif (len(commandArgs) == 2):
        playerName = commandArgs[1]
        if (not _checkPlayer(db, playerName)):
            return "Unknown player."
        ps = PlayerStats(playerName)
        ps.tally('red', 'black', db)
        ps.tally('black', 'red', db)
        if (client == "slack"):
            result = ""
            for cat in (("", ""), ("with", ""), ("as", "red"), ("as", "black")):
                result += ps.typeToString(cat[0], cat[1])
            return result
        else:
            return jsonify(ps.toDictionary())
    elif (len(commandArgs) == 3):
        playerName1 = commandArgs[1]
        if (not _checkPlayer(db, playerName1)):
            return "Unknown player 1."
        playerName2 = commandArgs[2]
        if (not _checkPlayer(db, playerName2)):
            return "Unknown player 2."
        ps = PlayerStats(playerName1)
        ps.tally('red', 'black', db)
        ps.tally('black', 'red', db)
        player2Id = str(_playerId(db, playerName2))
        if (client == "slack"):
            result = ps.typeToString("against", player2Id, True)
            result += ps.typeToString("with", player2Id, True)
            return result
        else:
            return jsonify({ "player" : playerName1, "otherPlayer" : playerName2, \
                             "pairStats" : [ ps.typeToDictionary("against", player2Id), ps.typeToDictionary("with", player2Id) ] })
    return "Invalid stats comand.  Use \"/foosball help\"."


class GameSide(object):
    def __init__(self, txt, color="", defense="", offense="", score=-1):
        if (txt is not None  and  len(txt) > 0):
            self.valid = self.parse(txt)
        if (defense is not None  and  len(defense) > 0):
            self.p1 = defense
        if (offense is not None  and  len(offense) > 0):
            self.p2 = offense
        if (color is not None  and  len(color) > 0):
            self.p1pos = color + "D"
            self.p2pos = color + "O"
        if (score >= 0):
            self.score = str(score)

    def toString(self):
        result = "" 
        result += self.p1
        result += "(" + (self.p1pos if (self.p1 != self.p2) else self.p1pos[:-1]) + ")"
        if (self.p1 != self.p2):
            result += "+" + self.p2
            result += "(" + self.p2pos + ")"
        result += ":" + str(self.score)
        return result

    def checkPosition(self, pos):
        return (pos == "red"  or  pos == "black"  or  pos == "redO"  or  pos == "redD"  or  pos == "blackO"  or  pos == "blackD")

    def parse(self, txt):
        mm = re.search('([^(]+)\(([^)]+)\)(\+([^(]+)\(([^)]+)\))?:(\d+)', txt)
        if (mm is not None):
            self.p1 = mm.group(1)
            self.p1pos = mm.group(2)
            self.p2 = mm.group(4)
            self.p2pos = mm.group(5)
            self.score = mm.group(6)
            if (int(self.score) < 0):
                return False
            if (not self.checkPosition(self.p1pos)  or  (self.p2pos is not None  and  not self.checkPosition(self.p2pos))):
                return False
            return True
        return False


def _game(commandArgs, db, user):
    if (not _sqlOk(user)):
        abort(401)
    if (len(commandArgs) != 3):
        return "game comand takes two arguments.  Use \"/foosball help\"."
    firstSide = GameSide(commandArgs[1])
    secondSide = GameSide(commandArgs[2])
    if (not firstSide.valid  or  not secondSide.valid):
        return "Invalid arguments to game command.  Use \"/foosball help\"."
    s1p1id = _playerId(db, firstSide.p1)
    s1p2id = s1p1id if (firstSide.p2 is None) else _playerId(db, firstSide.p2)
    if (s1p1id == -1  or  s1p2id == -1):
        return "Unknown player on first team.\n"
    s2p1id = _playerId(db, secondSide.p1)
    s2p2id = s2p1id if (secondSide.p2 is None) else _playerId(db, secondSide.p2)
    if (s1p1id == -1  or  s2p2id == -1):
        return "Unknown player on second team.\n"
    cursor = db.cursor()
    sql = "INSERT INTO Game (timestamp, recordedBy, redScore, blackScore, redDefense, redOffense, blackDefense, blackOffense) VALUES ("
    sql += "'" + datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S") + "'"
    sql += ",'" + user + "'"
    redMargin = 0
    if (firstSide.p1pos.startswith("red")):
        sql += "," + str(firstSide.score)
        sql += "," + str(secondSide.score)
        redMargin = int(firstSide.score) - int(secondSide.score)
        redDefense = s1p1id
        redOffense = s1p2id
        blackDefense = s2p1id
        blackOffense = s2p2id
    else:
        sql += "," + str(secondSide.score)
        sql += "," + str(firstSide.score)
        redMargin = int(secondSide.score) - int(firstSide.score)
        redDefense = s2p1id
        redOffense = s2p2id
        blackDefense = s1p1id
        blackOffense = s1p2id
    sql += "," + str(redDefense)
    sql += "," + str(redOffense)
    sql += "," + str(blackDefense)
    sql += "," + str(blackOffense)
    sql += ")"
    try:
        cursor.execute(sql)
        db.commit()
    except Exception as e:
        db.rollback()
        app.logger.error("Caught exception trying to insert into Game table:  " + str(e))
        return "Game NOT recorded.  Something went wrong."
    _postSlackMessage(user + " recorded game:  " + commandArgs[1] + " " + commandArgs[2])
    if (random.randint(1, 5) >= 5 - abs(redMargin)):
        if (redMargin > 0):
            _postInsult(db, [redOffense, redDefense][random.randint(0, 1)], [blackOffense, blackDefense][random.randint(0, 1)], 'black')
        else:
            _postInsult(db, [blackOffense, blackDefense][random.randint(0, 1)], [redOffense, redDefense][random.randint(0, 1)], 'red')
    return "Game recorded."



def _recent(commandArgs, db, user, client = "slack"):
    if (len(commandArgs) != 1):
        return "recent comand takes no arguments.  Use \"/foosball help\"."
    cursor = db.cursor()
    try:
        rows = []
        cursor.execute("SELECT * FROM Game as G WHERE timestamp > DATE_SUB(CURDATE(), INTERVAL 1 DAY) ORDER BY timestamp DESC")
        maxSideLen = 7
        maxAddedByLen = 7
        for row in cursor.fetchall():
            rows.append({ "gameid" : row[0], "timestamp" : row[1], "addedBy" : row[2], \
                          "side1" :  { "color" : "red", "defense" : _playerIdToName(db, row[5]), "offense" : _playerIdToName(db, row[6]), "score" : row[3] }, \
                          "side2" :  { "color" : "black", "defense" : _playerIdToName(db, row[7]), "offense" : _playerIdToName(db, row[8]), "score" : row[4] } })
            if (len(row[2]) > maxAddedByLen):
                maxAddedByLen = len(row[2])
            if (len(rows[-1]['side1']) > maxSideLen):
                maxSideLen = len(rows[-1]['side1'])
            if (len(rows[-1]['side2']) > maxSideLen):
                maxSideLen = len(rows[-1]['side2'])
        if (client == "slack"):
            addedBySpace = str(maxAddedByLen + 4)
            sideSpace = str(maxSideLen + 4) 
            formatStr = "%-6s\t%-32s\t%-" + sideSpace + "s\t%-" + sideSpace + "s\t%-" + addedBySpace + "s\n"
            result = formatStr % ("Game", "When", "Side 1", "Side 2", "Added By")
            formatStr = "%-6s\t\t%-16s\t%-" + sideSpace + "s\t%-" + sideSpace + "s\t%-" + addedBySpace + "s\n"
            for game in rows:
                result += formatStr % (str(game["gameid"]) + ':', str(game["timestamp"])[:-3], 
                                       GameSide("", game['side1']['color'], game['side1']['defense'], game['side1']['offense'], game['side1']['score']).toString(), \
                                       GameSide("", game['side2']['color'], game['side2']['defense'], game['side2']['offense'], game['side2']['score']).toString(), \
                                       game["addedBy"])
            return result
        else: 
            return jsonify({ "games" : rows })
    except Exception as e:
        app.logger.error("Caught exception trying to retrieve recent games:  " + str(e))
    return "Error!"


def _trash(commandArgs, db, user):
    result = "You're not good enough yet to trash talk!"
    if (len(commandArgs) != 1):
        return result
    cursor = db.cursor()
    try:
        cursor.execute("SELECT * FROM Game as G WHERE timestamp > DATE_SUB(CURDATE(), INTERVAL 1 DAY) ORDER BY timestamp DESC LIMIT 1")
        lastgame = cursor.fetchone()
        if (lastgame is None  or  len(lastgame) == 0):
            return result
        winner = -1
        loser = -1
        if (lastgame[3] > lastgame[4]):
            winner = lastgame[5 + random.randint(0, 1)]
            loser = lastgame[7 + random.randint(0, 1)]
            losingColor = 'black'
        elif (lastgame[3] < lastgame[4]):
            winner = lastgame[7 + random.randint(0, 1)]
            loser = lastgame[5 + random.randint(0, 1)]
            losingColor = 'red'
        if (loser != winner):
            _postInsult(db, winner, loser, losingColor)
            results = ["You're not so great yourself, you know.\n", "Feeling better?\n"]
            return results[random.randint(0, 1)]
    except Exception as e:
        app.logger.error("Caught exception trying to trash talk:  " + str(e))
    return result



############
## ROUTES ##
############

@app.route("/player", methods=['POST'])             ## Route used by web
def newPlayer():
    _startup()
    commandArgs = [ "player" ]
    if (not _addCommandArgsFromFlaskRequest("targetName", commandArgs)):
        abort(400)
    user = "a web user"
    db = _connectDB()
    try:
        if ("changeName" in request.form):
            commandArgs.append(request.form["changeName"])
            return _changePlayer(commandArgs, db, user)
        else:
            return _newPlayer(commandArgs, db, user)
    except Exception as e:
        app.logger.error("Caught exception in newPlayer():  " + str(e))
        return "Error!"
    finally:
        db.close()


@app.route("/players", methods=['GET'])             ## Route used by web
def getPlayers():
    _startup()
    commandArgs = [ "players" ]
    user = "a web user"
    db = _connectDB()
    try:
        return _getPlayers(commandArgs, db, user)
    except Exception as e:
        app.logger.error("Caught exception in getPlayers():  " + str(e))
        return "Error!"
    finally:
        db.close()


@app.route("/game", methods=['POST'])               ## Route used by web
def game():
    _startup()
    commandArgs = [ "game" ]
    if (not _addCommandArgsFromFlaskRequest([ "side1", "side2" ], commandArgs)):
        abort(400)
    user = "a web user"
    db = _connectDB()
    try:
        return _game(commandArgs, db, user)
    except Exception as e:
        app.logger.error("Caught exception in game():  " + str(e))
        return "Error!"
    finally:
        db.close()


@app.route("/stats", methods=['GET','POST'])        ## Route used by web
def stats():
    _startup()
    commandArgs = [ "stats" ]
    if (not _addCommandArgsFromFlaskRequest("playerName", commandArgs)):
        _addCommandArgsFromFlaskRequest(["playerName1", "playerName2"], commandArgs)
    user = "web"
    db = _connectDB()
    try:
        return _stats(commandArgs, db, user, "web")
    except Exception as e:
        app.logger.error("Caught exception in stats():  " + str(e))
        return "Error!"
    finally:
        db.close()


@app.route("/recent", methods=['GET','POST'])       ## Route used by web
def recent():
    _startup()
    commandArgs = [ "recent" ]
    user = "a web user"
    db = _connectDB()
    try:
        return _recent(commandArgs, db, user, "web")
    except Exception as e:
        app.logger.error("Caught exception in recent():  " + str(e))
        return "Error!"
    finally:
        db.close()


@app.route("/slack", methods=['POST'])              ## Route used by Slack
def slack():
    _readConfigFile()
    if (request.form['token'] != _g_config["slack"]["teamPayloadToken"]  or  request.form['team_domain'] != _g_config["slack"]["teamDomain"]):
        abort(401)
    _enableLogging()
    commandText = request.form['text']
    commandArgs = commandText.split()
    command = commandArgs[0]
    if (command == u"help"):
        help = "Valid commands:  help, newPlayer, stats, game, recent, changePlayer.\n"
        help += "\n"
        help += "To add a new player:  /foosball newPlayer [playerName]\n"
        help += "To change a player's name:  /foosball changePlayer [playerName] [newName]\n"
        help += "\n"
        help += "To get stats for all players:  /foosball stats\n"
        help += "To get stats for a player:  /foosball stats [playerName]\n"
        #help += "To get stats for a team:  /foosball stats [playerName1]+[playerName2]\n"
        help += "To get stats for a player against another player:  /foosball stats [playerName1] [playerName2]\n"
        help += "\n"
        help += "To add a 1-1 game record:  /foosball game steve(red):5 adriano(black):3\n"
        help += "To add a 2-2 game record:  /foosball game steve(redD)+daniel(redO):5 matt(blackO)+adriano(blackD):3\n"
        help += "\n"
        help += "To see all games added in last 24 hours:  /foosball recent\n"
        help += "There's also:  /foosball trash\n"
        help += "\n"
        return help

    user = request.form['user_name']
    db = _connectDB()
    
    try:
        if (command == u"stats"):
            return _stats(commandArgs, db, user)
        elif (command == u"recent"):
            return _recent(commandArgs, db, user)
        elif (command == u"game"):
            return _game(commandArgs, db, user)
        elif (command == u"newPlayer"):
            return _newPlayer(commandArgs, db, user)
        elif (command == u"changePlayer"):
            return _changePlayer(commandArgs, db, user)
        elif (command == u"trash"):
            return _trash(commandArgs, db, user)
        else:
            return "Invalid command.  Use \"/foosball help\"."
    except Exception as e:
        app.logger.error("Caught exception in slack():  " + str(e))
        return "Error!"
    finally:
        db.close()



######################
## MAIN ENTRY POINT ##
######################

if __name__ == "__main__":
  app.run()
