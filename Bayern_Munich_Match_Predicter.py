import requests
import json
from datetime import datetime
from sklearn.linear_model import LogisticRegression
import pandas as pd

url = "https://api.football-data.org/v4/"
response = requests.get(url=url)
api_key = "***"
headers = {"X-Auth-Token": api_key}

if response.status_code == 200:
    print("Error: Unable to reach the football data API")

def get_team_id(team_name, team_list):
    for team in team_list['teams']:
        if team['name'] == team_name or team['shortName'] == team_name:
            return int(team['id'])
    return None


def get_previous_matches(X_train, Y_train, standings, team_list):
    params = {"status": "FINISHED", "limit": 7}
    index = 0
    match_data = requests.get(url = f'{url}/teams/5/matches', headers = headers,params=params)
    matches = match_data.json()['matches']
    for match in reversed(matches):
        if int(match['competition']['id']) != 2002: 
            continue
        X_train_data = []
        if int(match['homeTeam']['id']) == 5:
            X_train_data.append(1)
            opponent_id = int(match['awayTeam']['id'])
            print(f'The opponent id is {opponent_id}')
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
    standing = requests.get(url = f'{url}competitions/BL1/standings', headers = headers, params=param)
    return standing.json()
        
def get_current_standing(team_id, standings):
    for standing in standings['standings'][0]['table']:
        if int(standing['team']['id']) == team_id:
            return int(standing['position'])


if __name__ == "__main__":    
    team = "Bayern"
    teams = requests.get(url = f'{url}/teams/', headers = headers)
    team_list = teams.json()
    standings = enter_standings()
    #next_match_team_id = get_next_match(team, team_list)
    # Win = 2, Draw = 1, Loss = 0
    # Home = 1, Away = 0
    
    X_train = []
    Y_train = []
    X_predict = []
    Y_predict = []
    get_previous_matches(X_train=X_train, Y_train=Y_train, standings=standings, team_list=team_list)
    print(X_train)
    print(Y_train)
    get_next_match(X_predict=X_predict, standings=standings)
    print(X_predict)
    model = LogisticRegression()
    model.fit(X=X_train, y=Y_train)

    prediction = model.predict(X=X_predict)
    print(f"Prediction: {prediction[0]}")
    probability = model.predict_proba(X=X_predict)
    results = pd.DataFrame({'Outcome': ['Loss', 'Draw', 'Win'], 'Probability': probability[0]})
    results['Probability'] = results['Probability'].apply(lambda x: f'{x:.2%}')
    print("\nProbabilities:")
    print(results.to_string(index=False))
