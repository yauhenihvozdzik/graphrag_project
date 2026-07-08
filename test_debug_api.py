import requests, sys

# Login
r = requests.post('http://localhost:8000/api/v1/auth/login', json={'email':'admin@graphrag.local','password':'Admin123!'})
token = r.json()['access_token']
print('TOKEN OK')

# Test users
r2 = requests.get('http://localhost:8000/api/v1/auth/users', headers={'Authorization': 'Bearer ' + token})
sys.stdout.write('USERS: ' + str(r2.status_code) + ' ' + r2.text[:500] + '\n')
sys.stdout.flush()

# Test departments
r3 = requests.get('http://localhost:8000/api/v1/departments/', headers={'Authorization': 'Bearer ' + token})
sys.stdout.write('DEPT: ' + str(r3.status_code) + ' ' + r3.text[:500] + '\n')
sys.stdout.flush()
