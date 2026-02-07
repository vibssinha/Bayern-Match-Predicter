import requests
import json
from datetime import datetime

url = "https://api.football-data.org/v4/"
response = requests.get(url=url)
api_key = "15f2988156244d89bdd77261ee5bb5b1"
headers = {"X-Auth-Token": api_key}

if response.status_code == 200:
    print("Error: Unable to reach the football data API")

def get_team_id(team_name):
    teams = requests.get(url = f'{url}/teams/', headers = headers)
    teams_data = teams.json()
    with open('teams.json', 'w') as f:
        json.dump(teams_data, f, indent=2)
    for team in teams_data['teams']:
        if team['name'] == team_name or team['shortName'] == team_name:
            return int(team['id'])
    return None


def get_previous_matches(team_name, data, team_ids):
    params = {"status": "FINISHED", "limit": 8}
    index = 0
    for team in data["Teams"]:
        team_id = team_ids[index]
        match_data = requests.get(url = f'{url}/teams/{team_id}/matches', headers = headers,params=params)
        for match in reversed(match_data.json()['matches']):
            if match['competition']['id'] != 2002: 
                continue
            if len(data['Previous Game Score'][index]) >= 5:
                break
            data["Previous Game Score"][index].append(f'{match['score']['fullTime']['home']} - {match['score']['fullTime']['away']}')
        index += 1

    return match_data.json()


def get_next_match(team_name):
    params = {"status": "SCHEDULED", "limit": 3}
    match_data = requests.get(url = f'{url}/teams/{get_team_id(team_name)}/matches', headers = headers,params=params)
    if match_data.status_code != 200:
        print("Error: Unable to fetch match data")
    index = 0
    while match_data.json()['matches'][index]['competition']['id'] != 2002:
        index += 1
    
    if match_data.json()['matches'][index]['awayTeam']['id'] == get_team_id(team_name):
        opponent_id = match_data.json()['matches'][index]['homeTeam']['id']
    else:
        opponent_id = match_data.json()['matches'][index]['awayTeam']['id']
    
    return opponent_id

def enter_standings(data):
    current_year = datetime.now().year
    if datetime.now().month < 8:
        current_year = current_year - 1
    index = 0
    param = {'season': f'{current_year}'}
    standing = requests.get(url = f'{url}competitions/BL1/standings', headers = headers, params=param)
    team_standing = standing.json()
    for team in data["Teams"]:
        team_id = get_team_id(team)
        for standing in team_standing['standings'][0]['table']:
            if standing['team']['id'] == team_id:
                data['Results'][index] = standing['form']
                data['Standing'][index] = standing['position']
                data['Goals Scored'][index] = int(standing['goalsFor'])
                data['Overall Record'][index] = f'{standing['won']} - {standing['draw']} - {standing['lost']}'
                data['Goals Against'][index] = int(standing['goalsAgainst'])
                data['Goal Differential'][index] = data['Goals Scored'][index] - data['Goals Against'][index]
                index = index + 1
                break
        



if __name__ == "__main__":    
    team = "Bayern"
    team_id = get_team_id(team)
    next_match_team_id = get_next_match(team)
    opponent = requests.get(url = f'{url}/teams/{next_match_team_id}', headers = headers)
    next_opponent = opponent.json()['name']
    team_ids = [team_id, next_match_team_id]
    data = {
        "Teams": [team, next_opponent],
        "Previous Game Score": [[],[]],
        "Results": [[],[]],
        "Standing": [[],[]],
        "Overall Record": [[],[]],
        "Goals Scored": [[],[]],
        "Goals Against": [[],[]],
        "Goal Differential":[[],[]]
    }
    matches = get_previous_matches(team, data, team_ids)
    enter_standings(data=data)
    print(data)
