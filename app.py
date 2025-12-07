# --------------------------------------------------------------------------------------
# app.py 파일 시작 (최종 통합본 - Heroku 배포 호환)
# --------------------------------------------------------------------------------------

# 1. 필수 라이브러리 Import
import os
import pandas as pd
from flask import Flask, request, render_template_string

# 🚨 경로 설정 (Heroku 환경에서는 os.getcwd()가 필요 없으나, 로컬 테스트를 위해 유지)
base_path = os.getcwd() 

# 2. 전역 변수 초기화
df_per_game = None      
df_standings = None     
players_list = None     

# 3. 데이터 로딩 함수 정의
def load_data():
    global df_per_game, df_standings, players_list
    
    # Heroku는 data 폴더를, 로컬은 base_path/data를 사용합니다.
    # Heroku 환경에서는 파일 시스템이 다를 수 있으므로 상대 경로를 사용합니다.
    data_path = os.path.join(base_path, 'data')

    try:
        # 데이터 파일 이름은 반드시 per_game.csv 및 standings.csv 여야 합니다.
        df_per_game = pd.read_csv(os.path.join(data_path, 'per_game.csv'))
        df_standings = pd.read_csv(os.path.join(data_path, 'standings.csv'))
        
        # 선수 이름 목록 생성
        players_list = sorted(df_per_game['Player'].unique().tolist())
        
        print("✅ 데이터 로딩 성공!")

    except FileNotFoundError as e:
        print(f"❌ 파일 로딩 실패: {e}. 'data' 폴더에 파일을 확인하세요.")
        players_list = []
        df_per_game = pd.DataFrame()
        df_standings = pd.DataFrame()
    except Exception as e:
        print(f"❌ 데이터 처리 중 오류 발생: {e}")
        players_list = []

# 4. 질문 파싱 함수 정의 (parse_question)
def parse_question(question):
    """
    사용자의 자연어 질문을 분석하여 의도(type)와 타겟(target, stat)을 추출합니다.
    """
    question = question.lower()
    parsed = {"type": "other", "target": None, "stat": None}
    
    # 랭킹/기록 관련 키워드
    if "득점 순위" in question or "득점 탑" in question or "득점 1위" in question:
        parsed["type"] = "ranking"
        parsed["stat"] = "PTS"
    elif "어시스트 순위" in question or "어시스트 탑" in question or "어시스트 1위" in question:
        parsed["type"] = "ranking"
        parsed["stat"] = "AST"
    elif "리바운드 순위" in question or "리바운드 탑" in question or "리바운드 1위" in question:
        parsed["type"] = "ranking"
        parsed["stat"] = "TRB"
    
    # 선수 기록 키워드
    for player in (players_list if players_list else []):
        if player.lower() in question:
            parsed["type"] = "player_stat"
            parsed["target"] = player
            break
            
    # 팀 명단 키워드
    if "선수 명단" in question or "멤버" in question or "선수 목록" in question:
        parsed["type"] = "roster"
        # 팀 약어 매핑 (예시)
        if "레이커스" in question or "lakers" in question:
            parsed["target"] = "LAL"
        elif "보스턴" in question or "celtics" in question:
            parsed["target"] = "BOS"
            
    # MVP/우승팀 키워드
    if "mvp" in question and ("정규시즌" in question or "시즌" in question):
        parsed["type"] = "award"
        parsed["target"] = "MVP"
    
    return parsed


# 5. 검색 결과 반환 함수 정의 (search_answer)
def search_answer(parsed):
    """
    파싱된 의도에 따라 데이터를 검색하고 결과를 문자열로 반환합니다.
    """
    global df_per_game, df_standings

    # 1. 랭킹 검색
    if parsed["type"] == "ranking" and parsed["stat"]:
        if df_per_game is None or df_per_game.empty:
            return "데이터가 로드되지 않았습니다."
            
        # 상위 5개 순위 추출 (시즌 통합)
        result_df = df_per_game.sort_values(by=parsed["stat"], ascending=False).head(5)
        
        answer = f"🏆 {parsed['stat']} 순위 TOP 5 (2023-24 시즌 기준):\n"
        
        # 순위를 1부터 시작하도록 인덱스 조정
        for i, row in result_df.iterrows():
            answer += f"{i+1}. {row['Player']} ({row['Tm']}) | 기록: {row[parsed['stat']]}\n"
        return answer
        
    # 2. 선수 기록 검색
    elif parsed["type"] == "player_stat" and parsed["target"]:
        if df_per_game is None or df_per_game.empty:
            return "데이터가 로드되지 않았습니다."
            
        player_data = df_per_game[df_per_game['Player'] == parsed["target"]].head(1)
        
        if not player_data.empty:
            row = player_data.iloc[0]
            answer = f"👤 {row['Player']} 선수 기록 (2023-24 시즌 기준):\n"
            answer += f"  - 소속 팀: {row['Tm']}\n"
            answer += f"  - 평균 득점 (PTS): {row['PTS']}\n"
            answer += f"  - 평균 어시스트 (AST): {row['AST']}\n"
            answer += f"  - 평균 리바운드 (TRB): {row['TRB']}\n"
            answer += f"  - 야투율 (FG%): {row['FG%']}\n"
            return answer
        else:
            return f"'{parsed['target']}' 선수의 기록을 찾을 수 없습니다. 이름이 정확한지 확인해주세요."

    # 3. 기타 질문에 대한 응답
    elif parsed["type"] == "roster":
        return f"요청하신 팀 '{parsed['target']}'의 선수 명단을 검색하는 로직입니다. (현재 로직 미구현)"
    elif parsed["type"] == "award":
        return "요청하신 MVP 수상자를 검색하는 로직입니다. (현재 로직 미구현)"
    else:
        return "🤔 현재 질문 유형은 지원하지 않습니다. 검색 가능한 질문 예시를 참고해주세요."


# 6. Flask 앱 인스턴스 생성 및 환경 변수 설정
# --------------------------------------------------------------------------------------
app = Flask(__name__, root_path=base_path, static_folder='static', static_url_path='/static')

# 7. 유튜브 링크 정의
YOUTUBE_LINKS = [
    {"name": "농알멋 - 스킬 트레이닝", "description": "농구 기술 마스터", "url": "https://www.youtube.com/@농알멋"},
    {"name": "Basketball Coach - 농구 전술 분석", "description": "공격/수비 전술", "url": "https://www.youtube.com/@basketball-coach"},
    {"name": "B_Story - NBA 경기 리뷰", "description": "최신 NBA 경기 분석", "url": "https://www.youtube.com/@B_Story"}
]

# 8. HTML 템플릿 (최종 카드 버전) 정의
HTML_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>🏀 NBA 질문 검색기</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #2c3e50;
            color: #ecf0f1;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            min-height: 100vh;
        }
        #background-slider {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-size: cover;
            background-position: center;
            opacity: 0.15;
            transition: background-image 2s ease-in-out;
            z-index: -1;
        }
        .main-wrapper {
            display: flex;
            flex-wrap: wrap; 
            width: 90%;
            max-width: 1400px;
            margin-top: 50px;
            gap: 30px;
        }
        .container {
            flex: 2;
            min-width: 500px; 
            background-color: rgba(44, 62, 80, 0.9);
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        }
        .player-list-section {
            flex: 1;
            min-width: 300px;
            background-color: rgba(44, 62, 80, 0.9);
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
            max-height: 80vh;
            overflow-y: auto;
        }
        /* 유튜브 카드 CSS */
        .youtube-cards-wrapper {
            display: flex;
            justify-content: space-between;
            margin-top: 40px;
            gap: 15px;
        }
        .youtube-card {
            flex: 1;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            color: #ecf0f1;
            transition: transform 0.2s, box-shadow 0.2s;
            cursor: pointer;
            text-decoration: none; 
        }
        .youtube-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.5);
        }
        .youtube-card h4 {
            margin: 5px 0 10px 0;
            font-size: 1.1em;
            color: #f1c40f;
        }
        .youtube-card p {
            font-size: 0.8em;
            color: #bdc3c7;
            margin-bottom: 0;
        }
        .youtube-icon {
            font-size: 2.5em;
            color: #e74c3c; 
            margin-bottom: 5px;
            display: block;
        }
        .bg-skill { background-color: #34495e; border-bottom: 3px solid #1abc9c; }
        .bg-tactics { background-color: #34495e; border-bottom: 3px solid #3498db; }
        .bg-review { background-color: #34495e; border-bottom: 3px solid #e74c3c; }
        /* 기존 CSS */
        h1 {
            color: #f1c40f;
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5em;
        }
        form {
            display: flex;
            margin-bottom: 20px;
        }
        input[type="text"]#question_input {
            flex-grow: 1;
            padding: 15px;
            border: 2px solid #3498db;
            border-radius: 5px 0 0 5px;
            font-size: 1.1em;
            background-color: #34495e;
            color: #ecf0f1;
        }
        input[type="submit"] {
            padding: 15px 25px;
            background-color: #3498db;
            color: white;
            border: none;
            border-radius: 0 5px 5px 0;
            cursor: pointer;
            font-size: 1.1em;
            transition: background-color 0.3s;
        }
        input[type="submit"]:hover {
            background-color: #2980b9;
        }
        h2 {
            color: #2ecc71;
            border-bottom: 2px solid #2ecc71;
            padding-bottom: 10px;
            margin-top: 30px;
        }
        pre {
            background-color: #34495e;
            padding: 15px;
            border-radius: 5px;
            white-space: pre-wrap;
            word-wrap: break-word;
            font-size: 1.0em;
            line-height: 1.6;
        }
        .help-section {
            margin-top: 40px;
            padding: 15px;
            border: 1px dashed #f39c12;
            border-radius: 5px;
            background-color: rgba(243, 156, 18, 0.1);
        }
        .help-section h3 {
            color: #f39c12;
            margin-top: 0;
            border-bottom: 1px solid #f39c12;
            padding-bottom: 5px;
        }
        .help-section ul {
            list-style-type: none;
            padding-left: 0;
        }
        .help-section li {
            margin-bottom: 8px;
            font-size: 0.95em;
        }
        .help-section li strong {
            color: #ecf0f1;
        }
        .player-search-box {
            margin-bottom: 15px;
        }
        #playerSearch {
            width: calc(100% - 22px);
            padding: 10px;
            border: 1px solid #7f8c8d;
            border-radius: 5px;
            background-color: #34495e;
            color: #ecf0f1;
            font-size: 1em;
        }
        .player-names-container {
            margin-top: 10px;
        }
        .player-name {
            display: inline-block;
            margin: 4px;
            padding: 5px 8px;
            background-color: #34495e;
            color: #bdc3c7;
            border-radius: 3px;
            cursor: pointer;
            font-size: 0.85em;
            transition: background-color 0.2s, color 0.2s;
        }
        .player-name:hover {
            background-color: #1abc9c;
            color: #2c3e50;
        }
        /* 모바일 반응형 */
        @media (max-width: 900px) {
            .main-wrapper {
                flex-direction: column;
                margin-top: 20px;
                width: 95%;
            }
            .container, .player-list-section {
                min-width: 100%;
                margin-top: 20px;
            }
            .youtube-cards-wrapper {
                flex-direction: column;
            }
            .player-list-section {
                max-height: 50vh; 
            }
        }
    </style>
</head>
<body>
    <div id="background-slider"></div>
    <div class="main-wrapper">
        <div class="container">
            <h1>🏀 NBA 질문 검색기 😎</h1>
            <form method="post">
                <input type="text" id="question_input" name="question" placeholder="예: 2023년 득점 순위 탑3는? 또는 2022년 레이커스 선수 명단은?" value="{{ request.form.question if request.form.question else '' }}">
                <input type="submit" value="검색">
            </form>
            {% if answer %}
            <h2>결과:</h2>
            <pre>{{ answer }}</pre>
            {% endif %}
            
            <div class="help-section">
                <h3>🔍 검색 가능한 질문 예시 (시즌: 2019-2020 ~ 2023-2024)</h3>
                <ul>
                    <li><strong>선수 기록:</strong> 2023년 르브론 제임스 평균 득점은? / 2021년 '선수이름' 어시스트 기록?</li>
                    <li><strong>시즌 랭킹:</strong> 2022년 득점 순위 탑3는? / 2024년 3점슛 1위는?</li>
                    <li><strong>팀 정보:</strong> 2021년 보스턴 셀틱스 선수 명단은? / 2020년 밀워키 벅스 멤버?</li>
                    <li><strong>팀 랭킹:</strong> 2020년 동부 컨퍼런스 1위 팀은? / 2023년 서부 3위 팀?</li>
                    <li><strong>수상 기록:</strong> 2023년 정규시즌 MVP는?</li>
                    <li><strong>우승팀:</strong> 2020년 NBA 우승팀은?</li>
                </ul>
            </div>
            
            <div class="youtube-cards-wrapper">
                
                <a href="{{ youtube_links[0].url }}" target="_blank" class="youtube-card bg-skill">
                    <span class="youtube-icon">🏀</span>
                    <h4>{{ youtube_links[0].name }}</h4>
                    <p>{{ youtube_links[0].description }}</p>
                </a>
                
                <a href="{{ youtube_links[1].url }}" target="_blank" class="youtube-card bg-tactics">
                    <span class="youtube-icon">🧠</span>
                    <h4>{{ youtube_links[1].name }}</h4>
                    <p>{{ youtube_links[1].description }}</p>
                </a>
                
                <a href="{{ youtube_links[2].url }}" target="_blank" class="youtube-card bg-review">
                    <span class="youtube-icon">🔥</span>
                    <h4>{{ youtube_links[2].name }}</h4>
                    <p>{{ youtube_links[2].description }}</p>
                </a>
                
            </div>
            
        </div>
        
        <div class="player-list-section">
            <h3>📋 선수 이름 목록 (클릭하면 복사됩니다!)</h3>
            <div class="player-search-box">
                <input type="text" id="playerSearch" placeholder="선수 이름 검색..." onkeyup="filterPlayers()">
            </div>
            <div class="player-names-container">
                {% if players and players != ["로딩 중..."] %}
                    <div class="all-players">  
                        {% for player in players %}
                            <span class="player-name" data-player-name="{{ player }}" onclick="copyToClipboard('{{ player }}')">{{ player }}</span>
                        {% endfor %}
                    </div>
                {% else %}
                    <p style="color: #f1c40f;">선수 명단을 백그라운드에서 로딩 중입니다...</p>
                    <p style="font-size: 0.9em; color: #bdc3c7;">(잠시 후 새로고침하거나 기다려주세요.)</p>
                {% endif %}
            </div>
        </div>
        
    </div>
    <script>
        const backgroundSlider = document.getElementById('background-slider');
        let currentImageIndex = 0;
        const images = [
            "/static/images/11.jpg", 
            "/static/images/22.jpg",
            "/static/images/33.jpg",
            "/static/images/44.jpg"
        ];
        
        function copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(() => {
                alert("'" + text + "'가 클립보드에 복사되었습니다!");
            }).catch(err => {
                console.error('클립보드 복사 실패:', err);
                prompt("Ctrl+C를 눌러 복사하세요:", text);
            });
        }

        function filterPlayers() {
            const input = document.getElementById('playerSearch');
            const filter = input.value.toUpperCase();
            const players = document.getElementsByClassName('player-name');
            for (let i = 0; i < players.length; i++) {
                const name = players[i].getAttribute('data-player-name');
                if (name.toUpperCase().indexOf(filter) > -1) {
                    players[i].style.display = "";
                } else {
                    players[i].style.display = "none";
                }
            }
        }

        function changeBackgroundImage() {
            if (images.length > 0) {
                backgroundSlider.style.backgroundImage = `url('${images[currentImageIndex]}')`;
                currentImageIndex = (currentImageIndex + 1) % images.length;
            }
        }

        window.onload = function() {
            changeBackgroundImage();
            setInterval(changeBackgroundImage, 3000);
        };
    </script>
</body>
</html>
"""

# 9. 라우팅 함수 정의
@app.route("/", methods=["GET", "POST"])
def index():
    answer = ""
    
    # POST 요청 처리
    if request.method == "POST":
        question = request.form["question"]
        try:
            # parse_question, search_answer 함수 호출
            parsed = parse_question(question)
            answer = search_answer(parsed)
        except Exception as e:
            answer = f"❌ 검색 중 오류가 발생했습니다: {e}"
            
    # players_list가 로드되었는지 확인하여 템플릿에 전달
    players_to_display = players_list if players_list is not None else ["로딩 중..."]
        
    # 유튜브 링크와 플레이어 목록을 템플릿으로 전달합니다.
    return render_template_string(HTML_TEMPLATE, 
                                  answer=answer, 
                                  players=players_to_display, 
                                  youtube_links=YOUTUBE_LINKS)

# 10. 초기 데이터 로딩
# Heroku는 이 부분에서 데이터를 로드하고 웹 서버(gunicorn)를 시작합니다.
load_data() 

if __name__ == "__main__":
    # 로컬 테스트용 실행 구문
    print("======================================================================")
    print("✅ Flask 서버 시작 완료. 로컬 테스트를 위해 아래 주소로 접속하세요:")
    print("   👉 http://127.0.0.1:5000/")
    print("======================================================================")
    # Heroku 배포 시에는 gunicorn이 실행하므로 이 부분은 로컬 테스트용입니다.
    app.run(host='0.0.0.0', port=5000, debug=True)

# --------------------------------------------------------------------------------------
# app.py 파일 끝
# --------------------------------------------------------------------------------------