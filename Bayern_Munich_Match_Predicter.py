import requests
import json
import sqlite3
from datetime import datetime
from sklearn.linear_model import LogisticRegression
import pandas as pd
import numpy as np

url = "https://api.football-data.org/v4/"
api_key = "15f2988156244d89bdd77261ee5bb5b1"
headers = {"X-Auth-Token": api_key}


#Setup database
def init_db():
    conn = sqlite3.connect('bayern_matches.db')
    con = conn.cursor()

    #1 = home game, 2 = away game
    #2 = win, 1 = draw, 0 = loss
    #match table
    con.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            season          INTEGER NOT NULL,
            home_team_id    INTEGER NOT NULL,
            away_team_id    INTEGER NOT NULL,
            is_home         INTEGER NOT NULL,   
            opponent_id     INTEGER NOT NULL,
            opponent_standing INTEGER NOT NULL,
            result          INTEGER NOT NULL,
            match_date      TEXT,
            UNIQUE(season, home_team_id, away_team_id, match_date)
        )
    ''')

    #standings table
    con.execute('''
        CREATE TABLE IF NOT EXISTS standings (
            team_id  INTEGER NOT NULL,
            season   INTEGER NOT NULL,
            position INTEGER NOT NULL,
            PRIMARY KEY (team_id, season)
        )
    ''')

    conn.commit()
    return conn


def enter_standings(conn):
    #Get the current year
    current_year = datetime.now().year
    if datetime.now().month < 8:
        current_year = current_year - 1

    #Set up seasons and results
    seasons = [current_year, current_year - 1, current_year - 2]
    results = []

    for season in seasons:
        # Check the database first
        c = conn.cursor()
        c.execute('SELECT team_id, position FROM standings WHERE season = ?', (season,))
        rows = c.fetchall()

        if rows:
            # If th data exists build the standings table from that (save api call)
            standings_dict = _build_standings_dict_from_cache(rows, season)
        else:
            # Otherwise get api call
            resp = requests.get(
                url=f'{url}competitions/BL1/standings',
                headers=headers,
                params={'season': f'{season}'}
            )
            standings_dict = resp.json()
            #insert the new values into the database
            _db_standings(conn, standings_dict, season)

        results.append(standings_dict)

    return results[0], results[1], results[2]


def _db_standings(conn, standings_json, season):
    c = conn.cursor()
    for entry in standings_json['standings'][0]['table']:
        c.execute(f"INSERT OR REPLACE INTO standings (team_id, season, position) VALUES ({int(entry['team']['id'])}, {season}, {int(entry['position'])})")
    conn.commit()


def _build_standings_dict_from_cache(rows, season):
    table = [{'team': {'id': team_id}, 'position': position} for team_id, position in rows]
    return {
        'filters': {'season': str(season)},
        'standings': [{'table': table}]
    }


def get_current_standing(team_id, standings):
    for entry in standings['standings'][0]['table']:
        if int(entry['team']['id']) == team_id:
            return int(entry['position'])



def get_previous_matches(conn, X_train, Y_train, standings, year):
    c = conn.cursor()
    c.execute(
        'SELECT is_home, opponent_standing, result FROM matches WHERE season = ?',
        (year,)
    )
    cached_rows = c.fetchall()
    if cached_rows:
        print(f"Loading {len(cached_rows)} matches for season {year}")
        for is_home, opp_standing, result in cached_rows:
            X_train.append([is_home, opp_standing])
            Y_train.append(result)
        return
 
    # Not in database – fetch from API
    params = {"status": "FINISHED", "season": year}
    match_data = requests.get(url=f'{url}/teams/5/matches', headers=headers, params=params)
    matches = match_data.json()['matches']
    rows_to_insert = []
 
    for match in matches:
        if int(match['competition']['id']) != 2002:
            continue
        X_train_data = []
        home_id = int(match['homeTeam']['id'])
        away_id = int(match['awayTeam']['id'])
        match_date = match.get('utcDate', '')
 
        if home_id == 5:
            X_train_data.append(1)
            opponent_id = away_id
            opponent_current_standing = get_current_standing(team_id=opponent_id, standings=standings)
            X_train_data.append(opponent_current_standing)
            if match['score']['winner'] == 'HOME_TEAM':
                Y_train.append(2)
                result = 2
            elif match['score']['winner'] == 'DRAW':
                Y_train.append(1)
                result = 1
            else:
                Y_train.append(0)
                result = 0
        else:
            X_train_data.append(0)
            opponent_id = home_id
            opponent_current_standing = get_current_standing(team_id=opponent_id, standings=standings)
            X_train_data.append(opponent_current_standing)
            if match['score']['winner'] == 'AWAY_TEAM':
                Y_train.append(2)
                result = 2
            elif match['score']['winner'] == 'DRAW':
                Y_train.append(1)
                result = 1
            else:
                Y_train.append(0)
                result = 0
 
        X_train.append(X_train_data)
        rows_to_insert.append((year, home_id, away_id, X_train_data[0], opponent_id, opponent_current_standing, result, match_date))
 
    # Bulk insert the values into database
    c.executemany('''
        INSERT OR IGNORE INTO matches
            (season, home_team_id, away_team_id, is_home, opponent_id, opponent_standing, result, match_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', rows_to_insert)
    conn.commit()
    print(f"  Inserted {len(rows_to_insert)} matches for season {year}")



def get_next_match(X_predict, standings):
    params = {"status": "SCHEDULED", "limit": 3}
    resp = requests.get(url=f'{url}/teams/5/matches', headers=headers, params=params)
    match_data = resp.json()

    if resp.status_code != 200:
        print("Error: Unable to fetch upcoming match data")
        return

    index = 0
    while match_data['matches'][index]['competition']['id'] != 2002:
        index += 1

    match = match_data['matches'][index]
    if match['awayTeam']['id'] == 5:
        opponent_id = match['homeTeam']['id']
        is_home = 0
    else:
        opponent_id = match['awayTeam']['id']
        is_home = 1

    X_predict.append([is_home, get_current_standing(opponent_id, standings)])
    if match['awayTeam']['id'] == 5:
        return match['homeTeam']['name']
    else:
        return match['awayTeam']['name']




if __name__ == "__main__":
    conn = init_db()

    print("Loading standings...")
    current_standings, one_year_past, two_year_past = enter_standings(conn)

    # Win = 2, Draw = 1, Loss = 0 and Home = 1, Away = 0
    X_train, Y_train = [], []
    X_predict = []

    print("\nLoading training data:")
    get_previous_matches(conn, X_train, Y_train, two_year_past,  int(two_year_past['filters']['season']))
    get_previous_matches(conn, X_train, Y_train, one_year_past,  int(one_year_past['filters']['season']))
    get_previous_matches(conn, X_train, Y_train, current_standings, int(current_standings['filters']['season']))

    print("\nFetching next match against " + get_next_match(X_predict, current_standings))
    

    # This creates an exponential sample weight where the more recent matches are given higher priority/have more weight
    sample_size = len(X_train)
    weights = np.exp(np.linspace(-2, 0, sample_size))

    model = LogisticRegression()
    model.fit(X=X_train, y=Y_train, sample_weight=weights)
    prediction = model.predict(X=X_predict)
    probability = model.predict_proba(X=X_predict)

    outcome_map = {0: 'Loss', 1: 'Draw', 2: 'Win'}
    print(f"\nPrediction: {outcome_map[prediction[0]]}")

    results = pd.DataFrame({
        'Outcome': ['Loss', 'Draw', 'Win'],
        'Probability': probability[0]
    })
    results['Probability'] = results['Probability'].apply(lambda x: f'{x:.2%}')
    print("\nProbabilities:")
    print(results.to_string(index=False))

    conn.close()
