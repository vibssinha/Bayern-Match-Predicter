import os
import requests
import json
import sqlite3
import webbrowser
from datetime import datetime
from sklearn.linear_model import LogisticRegression
import pandas as pd
import numpy as np

url = "https://api.football-data.org/v4/"
api_key = "***"
headers = {"X-Auth-Token": api_key}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, 'template.html')
REPORT_PATH = os.path.join(SCRIPT_DIR, 'bayern_prediction.html')


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

    # Not in database â€“ fetch from API
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
    """Fetch Bayern's next Bundesliga fixture and return everything the
    front end needs: opponent identity, crest URLs, standings, and the
    feature row appended to X_predict for the model."""
    params = {"status": "SCHEDULED", "limit": 3}
    resp = requests.get(url=f'{url}/teams/5/matches', headers=headers, params=params)
    match_data = resp.json()

    if resp.status_code != 200:
        print("Error: Unable to fetch upcoming match data")
        return None

    index = 0
    while match_data['matches'][index]['competition']['id'] != 2002:
        index += 1

    match = match_data['matches'][index]
    home_team = match['homeTeam']
    away_team = match['awayTeam']

    if away_team['id'] == 5:
        is_home = 0
        opponent = home_team
        bayern_crest = away_team.get('crest', '')
    else:
        is_home = 1
        opponent = away_team
        bayern_crest = home_team.get('crest', '')

    opponent_standing = get_current_standing(team_id=opponent['id'], standings=standings)
    X_predict.append([is_home, opponent_standing])

    return {
        'opponent_name': opponent['name'],
        'opponent_crest': opponent.get('crest', ''),
        'opponent_standing': opponent_standing,
        'bayern_crest': bayern_crest,
        'is_home': is_home,
        'match_date_display': _format_match_date(match.get('utcDate', '')),
    }


def _format_match_date(utc_date_str):
    if not utc_date_str:
        return 'Date TBD'
    try:
        dt = datetime.strptime(utc_date_str, '%Y-%m-%dT%H:%M:%SZ')
        return dt.strftime('%a, %b %d, %Y Â· %I:%M %p UTC')
    except ValueError:
        return utc_date_str


def _ordinal(n):
    if n is None:
        return ''
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f'{n}{suffix}'


def _team_initials(name):
    words = [w for w in name.split() if w.isalpha()]
    if not words:
        return name[:3].upper()
    if len(words) == 1:
        return words[0][:3].upper()
    return ''.join(w[0] for w in words[:3]).upper()


def _crest_html(crest_url, fallback_text):
    if crest_url:
        return f'<img src="{crest_url}" alt="{fallback_text} crest">'
    return f'<div class="crest-fallback">{fallback_text}</div>'


def generate_html_report(match_info, win_pct, draw_pct, loss_pct, current_standings):
    """Fill template.html with this run's prediction and write out a
    ready-to-open bayern_prediction.html next to this script."""
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    bayern_standing = get_current_standing(5, current_standings)

    replacements = {
        '__HOME_CLASS__': 'home-game' if match_info['is_home'] else 'away-game',
        '__OPPONENT_NAME__': match_info['opponent_name'],
        '__MATCH_DATE__': match_info['match_date_display'],
        '__VENUE_LABEL__': 'Home' if match_info['is_home'] else 'Away',
        '__BAYERN_LOGO__': _crest_html(match_info['bayern_crest'], 'FCB'),
        '__OPPONENT_LOGO__': _crest_html(match_info['opponent_crest'], _team_initials(match_info['opponent_name'])),
        '__BAYERN_STANDING__': f'Bundesliga Â· {_ordinal(bayern_standing)}' if bayern_standing else 'Bundesliga',
        '__OPPONENT_STANDING__': f"Bundesliga Â· {_ordinal(match_info['opponent_standing'])}" if match_info['opponent_standing'] else 'Bundesliga',
        '__WIN_PCT__': f'{win_pct * 100:.0f}',
        '__DRAW_PCT__': f'{draw_pct * 100:.0f}',
        '__LOSS_PCT__': f'{loss_pct * 100:.0f}',
    }

    for token, value in replacements.items():
        html = html.replace(token, str(value))

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)

    return REPORT_PATH




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

    match_info = get_next_match(X_predict, current_standings)
    if match_info is None:
        raise SystemExit("Could not determine the next match.")
    print("\nFetching next match against " + match_info['opponent_name'])

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

    # probability[0] is ordered [Loss, Draw, Win] to match model.classes_
    loss_pct, draw_pct, win_pct = probability[0]
    report_path = generate_html_report(match_info, win_pct, draw_pct, loss_pct, current_standings)
    print(f"\nSaved matchday forecast page to {report_path}")
    try:
        webbrowser.open(f'file://{report_path}')
    except Exception:
        pass

    conn.close()
