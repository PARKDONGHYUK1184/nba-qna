import pandas as pd
import re
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime

# 데이터 로딩
try:
    # Heroku 환경에서는 파일 경로가 다를 수 있으므로 현재 디렉토리에서 찾습니다.
    # 만약 에러가 발생하면 절대 경로를 사용해야 할 수도 있습니다.
    per_game_df = pd.read_csv('per_game.csv')
    standings_df = pd.read_csv('standings.csv')
    
    # 선수 이름 전처리: 검색을 용이하게 하기 위해 소문자화 및 공백 제거
    per_game_df['Player_lower'] = per_game_df['Player'].str.lower().str.replace('[^a-zA-Z\s]', '', regex=True).str.strip()
    
    data_loaded = True
    print("DEBUG: 데이터 파일(per_game.csv, standings.csv) 로드 성공")
except FileNotFoundError:
    data_loaded = False
    print("ERROR: 데이터 파일을 찾을 수 없습니다. per_game.csv와 standings.csv를 확인하세요.")
except Exception as e:
    data_loaded = False
    print(f"ERROR: 데이터 로드 중 오류 발생: {e}")


app = Flask(__name__)

# --- 데이터 검색 함수 ---

def search_player_stats(player_name, season):
    """특정 선수의 특정 시즌 주요 기록을 검색합니다."""
    
    # season 형식 처리 (예: '2023-24')
    if not re.match(r'\d{4}-\d{2}', season):
        print(f"DEBUG: 잘못된 시즌 형식: {season}")
        return None
    
    # 선수 이름 전처리
    player_lower = player_name.lower().replace('[^a-zA-Z\s]', '', regex=True).strip()

    # 데이터 프레임에서 검색
    result = per_game_df[(per_game_df['Player_lower'] == player_lower) & (per_game_df['Season'] == season)]
    
    if result.empty:
        return f"ERROR: {season} 시즌 {player_name} 선수의 기록을 찾을 수 없습니다. 이름이나 시즌을 확인해 주세요."
    
    # 필요한 주요 기록만 추출 및 포맷팅
    stats = result.iloc[0]
    output = f"""
    ### 🏀 {season} 시즌 {stats['Player']} 주요 기록
    - **소속팀**: {stats['Tm']}
    - **경기 수**: {stats['G']}
    - **출전 시간 (MP)**: {stats['MP']:.1f}
    - **득점 (PTS)**: {stats['PTS']:.1f}
    - **리바운드 (TRB)**: {stats['TRB']:.1f}
    - **어시스트 (AST)**: {stats['AST']:.1f}
    - **FG%**: {stats['FG%']:.3f}
    - **3P%**: {stats['3P%']:.3f}
    """
    return output

def search_top_players(season, stat_category, top_n=5):
    """특정 시즌 특정 스탯 카테고리의 TOP N 선수를 검색합니다."""
    
    # Stat 카테고리 매핑 (사용자 친화적인 이름 -> CSV 컬럼 이름)
    stat_map = {
        '득점': 'PTS', '리바운드': 'TRB', '어시스트': 'AST',
        '스틸': 'STL', '블록': 'BLK', '자유투': 'FT'
    }
    
    column = stat_map.get(stat_category.upper(), None) # 대소문자 무시
    
    if not column:
        return f"ERROR: 지원하지 않는 스탯 카테고리 ({stat_category})입니다. (득점, 리바운드, 어시스트 등만 가능)"

    # 데이터 프레임에서 검색
    try:
        top_players = per_game_df[per_game_df['Season'] == season].sort_values(by=column, ascending=False).head(top_n)
    except KeyError:
        return f"ERROR: {season} 시즌 데이터를 찾을 수 없거나 스탯 컬럼 이름({column})에 오류가 있습니다."
        
    if top_players.empty:
        return f"ERROR: {season} 시즌의 TOP {top_n} 선수 기록을 찾을 수 없습니다."

    # 결과 포맷팅
    output = f"### 🏆 {season} 시즌 {stat_category.upper()} TOP {top_n} 선수\n\n"
    for i, row in top_players.iterrows():
        output += f"**{i+1}. {row['Player']}** ({row['Tm']}): {column} {row[column]:.1f}\n"
        
    return output

def get_team_standings(season, conference):
    """특정 시즌 특정 컨퍼런스의 팀 순위를 검색합니다."""
    
    # 컨퍼런스 이름 정규화
    conference = conference.lower().replace('동부', 'East').replace('서부', 'West')
    
    if conference not in ['east', 'west']:
        return "ERROR: 컨퍼런스는 '동부' 또는 '서부'만 입력할 수 있습니다."

    # 데이터 프레임에서 검색
    standings = standings_df[(standings_df['Season'] == season) & (standings_df['Conference'] == conference)].sort_values(by='Rk', ascending=True)
    
    if standings.empty:
        return f"ERROR: {season} 시즌 {conference} 컨퍼런스 순위를 찾을 수 없습니다."

    # 결과 포맷팅
    output = f"### 📊 {season} 시즌 {conference.upper()} 컨퍼런스 순위\n\n"
    for i, row in standings.iterrows():
        output += f"**{int(row['Rk'])}. {row['Team']}** (승/패: {row['W']}/{row['L']}, 승률: {row['W/L']:.3f})\n"
        
    return output

# --- 메인 쿼리 처리 함수 ---

def handle_query(query):
    """사용자 쿼리를 분석하고 적절한 검색 함수를 호출합니다."""
    
    if not data_loaded:
        return "데이터 파일을 로드하는 데 실패하여 검색을 수행할 수 없습니다. 서버 로그를 확인하세요."
        
    # 쿼리 전처리
    query = query.lower().strip()
    
    # --- 1. 시즌 및 선수 기록 조회 (예: '2023-24 시즌 르브론 제임스 득점 순위는?') ---
    match_player_stats = re.search(r'(\d{4}-\d{2}) 시즌 (.+?) (주요 기록|득점|리바운드|어시스트|순위)는?', query)
    if match_player_stats:
        season, player_name, category = match_player_stats.groups()
        player_name = player_name.strip()
        
        # '순위' 요청이 들어오면 TOP N 검색 함수로 리디렉션
        if '순위' in category:
            # 순위 검색을 위해 어떤 스탯 순위를 묻는지 추가적으로 파악해야 함
            # 예시 질문을 '2023-24 시즌 르브론 제임스 득점 순위는?' 와 같이 구체화해야 작동 가능
            stat_match = re.search(r'(.+?) (득점|리바운드|어시스트|스틸|블록) 순위는?', query)
            if stat_match:
                stat_category = stat_match.group(2)
                return search_top_players(season, stat_category, top_n=20) # 개인 순위는 TOP 20에서 찾아보도록 설정
        
        # '주요 기록' 요청 처리
        return search_player_stats(player_name, season)

    # --- 2. TOP N 선수 기록 조회 (예: '2023-24 시즌 득점 TOP 5 선수는?') ---
    match_top_n = re.search(r'(\d{4}-\d{2}) 시즌 (.+?) top (\d+) 선수는?', query)
    if match_top_n:
        season, stat_category, top_n = match_top_n.groups()
        stat_category = stat_category.strip()
        top_n = int(top_n)
        return search_top_players(season, stat_category, top_n)

    # --- 3. 팀 순위 조회 (예: '2023-24 시즌 동부 컨퍼런스 순위는?') ---
    match_standings = re.search(r'(\d{4}-\d{2}) 시즌 (동부|서부) 컨퍼런스 순위는?', query)
    if match_standings:
        season, conference = match_standings.groups()
        return get_team_standings(season, conference)
        
    # --- 매칭되는 유형이 없는 경우 ---
    example_queries = [
        "2023-24 시즌 르브론 제임스 주요 기록은?",
        "2023-24 시즌 득점 TOP 5 선수는?",
        "2023-24 시즌 동부 컨퍼런스 순위는?"
    ]
    return f"""
    ### ⚠️ 현재 질문 유형은 지원하지 않습니다.
    검색 가능한 질문 예시를 참고해주세요:
    - {example_queries[0]}
    - {example_queries[1]}
    - {example_queries[2]}
    """


# --- Flask 라우팅 ---

# 질문을 처리하는 API 엔드포인트 (프론트엔드 JavaScript에서 이 경로로 POST 요청을 보냄)
@app.route('/api/query', methods=['POST'])
def api_query():
    data = request.get_json()
    query = data.get('query', '')
    
    # 🚨 DEBUGGING: 어떤 쿼리가 들어왔는지 로그 출력
    print(f"DEBUG: Received query: {query}") 
    
    result = handle_query(query)
    
    # 🚨 DEBUGGING: 어떤 결과가 나가는지 로그 출력
    print(f"DEBUG: Response result: {result[:50]}...")
    
    return jsonify({'result': result})


# 메인 페이지를 렌더링하는 엔드포인트
@app.route('/', methods=['GET', 'POST'])
def index():
    # POST 요청은 /api/query로 리디렉션되었으므로, 여기서는 GET 요청만 처리
    return render_template_string(HTML_TEMPLATE)


# --- HTML 템플릿 (JavaScript 수정 포함) ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NBA Q&A 챗봇</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Noto Sans KR', sans-serif;
            background-color: #f4f7f6;
            color: #333;
            margin: 0;
            padding: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container {
            background-color: #ffffff;
            width: 90%;
            max-width: 800px;
            margin: 40px auto;
            border-radius: 12px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }
        header {
            background-color: #1a1a1a;
            color: white;
            padding: 30px 20px;
            text-align: center;
            border-bottom: 5px solid #ff4500;
        }
        header h1 {
            margin: 0;
            font-size: 2em;
        }
        header p {
            margin-top: 5px;
            font-size: 0.9em;
            color: #ccc;
        }
        .chat-window {
            height: 500px;
            overflow-y: auto;
            padding: 20px;
            border-bottom: 1px solid #eee;
        }
        .message-box {
            margin-bottom: 15px;
            display: flex;
        }
        .message-box.user {
            justify-content: flex-end;
        }
        .message-box.bot {
            justify-content: flex-start;
        }
        .message {
            max-width: 70%;
            padding: 12px 18px;
            border-radius: 20px;
            line-height: 1.5;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        }
        .message.user {
            background-color: #ff4500;
            color: white;
            border-bottom-right-radius: 5px;
        }
        .message.bot {
            background-color: #e6e6e6;
            color: #333;
            border-bottom-left-radius: 5px;
        }
        .input-area {
            padding: 20px;
            display: flex;
            background-color: #f9f9f9;
        }
        .input-area input[type="text"] {
            flex-grow: 1;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 1em;
            margin-right: 10px;
            outline: none;
        }
        .input-area button {
            background-color: #1a1a1a;
            color: white;
            border: none;
            padding: 12px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            transition: background-color 0.3s;
        }
        .input-area button:hover {
            background-color: #333;
        }
        .message.bot pre {
            white-space: pre-wrap;
            word-wrap: break-word;
            font-family: 'Noto Sans KR', sans-serif;
            margin: 5px 0 0;
            padding: 0;
            background: none;
            border: none;
        }
        .message.bot h3 {
            margin-top: 0;
            color: #ff4500;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>NBA Q&A 챗봇</h1>
            <p>NBA 데이터를 기반으로 선수 기록, 순위 등을 알려드립니다.</p>
        </header>
        <div class="chat-window" id="chatWindow">
            <div class="message-box bot">
                <div class="message">
                    안녕하세요! NBA 데이터에 대해 궁금한 점을 질문해 주세요.<br><br>
                    **검색 예시:**
                    <br>- 2023-24 시즌 르브론 제임스 주요 기록은?
                    <br>- 2023-24 시즌 득점 TOP 5 선수는?
                    <br>- 2023-24 시즌 동부 컨퍼런스 순위는?
                </div>
            </div>
        </div>
        <div class="input-area">
            <input type="text" id="userInput" placeholder="질문을 입력하세요..." onkeydown="if(event.key === 'Enter') sendMessage()">
            <button onclick="sendMessage()">검색</button>
        </div>
    </div>

    <script>
        const chatWindow = document.getElementById('chatWindow');
        const userInput = document.getElementById('userInput');

        function addMessage(sender, text) {
            const messageBox = document.createElement('div');
            messageBox.classList.add('message-box', sender);

            const message = document.createElement('div');
            message.classList.add('message', sender);
            
            // Markdown 형식 처리를 위해 <pre> 태그 사용
            if (sender === 'bot') {
                const pre = document.createElement('pre');
                pre.innerHTML = text.replace(/\\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<b>$1</b>').replace(/###\s*(.*)/g, '<h3>$1</h3>').replace(/- (.*)/g, '• $1');
                message.appendChild(pre);
            } else {
                message.textContent = text;
            }

            messageBox.appendChild(message);
            chatWindow.appendChild(messageBox);
            chatWindow.scrollTop = chatWindow.scrollHeight;
        }

        async function sendMessage() {
            const query = userInput.value.trim();
            if (query === "") return;

            addMessage('user', query);
            userInput.value = ''; // 입력창 비우기

            // 챗봇 응답 대기 메시지
            addMessage('bot', '검색 중입니다...');
            const loadingMessage = chatWindow.lastChild.querySelector('.message');
            
            try {
                // 🚨🚨🚨 중요한 수정 부분: API 경로를 '/api/query'로 변경 🚨🚨🚨
                const response = await fetch('/api/query', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ query: query })
                });

                const data = await response.json();
                
                // 로딩 메시지 제거 후 실제 응답 표시
                chatWindow.removeChild(chatWindow.lastChild);
                addMessage('bot', data.result);
                
            } catch (error) {
                console.error('Fetch error:', error);
                chatWindow.removeChild(chatWindow.lastChild);
                addMessage('bot', '죄송합니다. 서버 통신 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
            }
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    # 로컬 테스트 시
    app.run(debug=True)