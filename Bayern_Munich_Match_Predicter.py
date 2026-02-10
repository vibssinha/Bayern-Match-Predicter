import requests
import json
from datetime import datetime
from sklearn.linear_model import LogisticRegression
import pandas as pd
import numpy as np

url = "https://api.football-data.org/v4/"
response = requests.get(url=url)
api_key = "****"
headers = {"X-Auth-Token": api_key}

if response.status_code == 200:
    print("Error: Unable to reach the football data API")


def get_previous_matches(X_train, Y_train, standings, year):
    params = {"status": "FINISHED", "season": year}
    index = 0
    match_data = requests.get(url = f'{url}/teams/5/matches', headers = headers,params=params)
    matches = match_data.json()['matches']
    for match in matches:
        if int(match['competition']['id']) != 2002: 
            continue
        X_train_data = []
        if int(match['homeTeam']['id']) == 5:
            X_train_data.append(1)
            opponent_id = int(match['awayTeam']['id'])
            opponent_current_standing = get_current_standing(team_id=opponent_id, standings=standings)
            X_train_data.append(opponent_current_standing)
            if match['score']['winner'] == 'HOME_TEAM':
                Y_train.append(2)
            elif match['score']['winner'] == 'DRAW':
                Y_train.append(1)
            else:
                Y_train.append(0)
        else:
            X_train_data.append(0)
            opponent_id = int(match['homeTeam']['id'])
            opponent_current_standing = get_current_standing(team_id=opponent_id, standings=standings)
            X_train_data.append(opponent_current_standing)
            if match['score']['winner'] == 'AWAY_TEAM':
                Y_train.append(2)
            elif match['score']['winner'] == 'DRAW':
                Y_train.append(1)
            else:
                Y_train.append(0)
        X_train.append(X_train_data)

    


def get_next_match(X_predict, standings):
    params = {"status": "SCHEDULED", "limit": 3}
    match = requests.get(url = f'{url}/teams/5/matches', headers = headers,params=params)
    match_data = match.json()
    if match.status_code != 200:
        print("Error: Unable to fetch match data")
    index = 0
    while match_data['matches'][index]['competition']['id'] != 2002:
        index += 1
    
    if match_data['matches'][index]['awayTeam']['id'] == 5:
        X_predict.append([0, get_current_standing(match_data['matches'][index]['homeTeam']['id'],standings)])
    else:
        X_predict.append([1, get_current_standing(match_data['matches'][index]['awayTeam']['id'],standings)])


def enter_standings():
    current_year = datetime.now().year
    if datetime.now().month < 8:
        current_year = current_year - 1
    index = 0
    param = {'season': f'{current_year}'}
    current_standing = requests.get(url = f'{url}competitions/BL1/standings', headers = headers, params=param)
    one_year_past_standings = requests.get(url = f'{url}competitions/BL1/standings', headers = headers, params={'season': f'{current_year - 1}'})
    two_year_past_standings = requests.get(url = f'{url}competitions/BL1/standings', headers = headers, params={'season': f'{current_year - 2}'})
    return current_standing.json(), one_year_past_standings.json(), two_year_past_standings.json()
        
def get_current_standing(team_id, standings):
    for standing in standings['standings'][0]['table']:
        if int(standing['team']['id']) == team_id:
            return int(standing['position'])


if __name__ == "__main__":    
    team = "Bayern"
    teams = requests.get(url = f'{url}/teams/', headers = headers)
    team_list = teams.json()
    current_standings, one_year_past_standing, two_year_past_standing = enter_standings()
    current_year = datetime.now().year
    #Win = 2, Draw = 1, Loss = 0
    #Home = 1, Away = 0
    X_train = []
    Y_train = []
    X_predict = []
    Y_predict = []
    get_previous_matches(X_train=X_train, Y_train=Y_train, standings=two_year_past_standing, year = int(two_year_past_standing['filters']['season']))
    get_previous_matches(X_train=X_train, Y_train=Y_train, standings=one_year_past_standing, year = int(one_year_past_standing['filters']['season']))
    get_previous_matches(X_train=X_train, Y_train=Y_train, standings=current_standings, year=int(current_standings['filters']['season']))

    get_next_match(X_predict=X_predict, standings=current_standings)
    sample_size = len(X_train)
    weights = np.exp(np.linspace(-2,0,sample_size))
    model = LogisticRegression()
    model.fit(X=X_train, y=Y_train, sample_weight=weights)
    prediction = model.predict(X=X_predict)
    print(f"Prediction: {prediction[0]}")
    probability = model.predict_proba(X=X_predict)
    results = pd.DataFrame({'Outcome': ['Loss', 'Draw', 'Win'], 'Probability': probability[0]})
    results['Probability'] = results['Probability'].apply(lambda x: f'{x:.2%}')
    print("\nProbabilities:")
    print(results.to_string(index=False))


   
