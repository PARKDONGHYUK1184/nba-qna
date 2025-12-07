import pandas as pd
import numpy as np
import os
import threading
import time
from flask import Flask, request, jsonify, render_template_string
from functools import lru_cache

# ----------------------------------------------------------------------
# 1. 설정 및 초기화
# ----------------------------------------------------------------------
app = Flask(__name__)
# 현재 실행 디렉토리를 기준으로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 🚨 파일 경로 설정 (data 폴더 안의 per_game.csv, standings.csv 사용)
PLAYER_DATA_PATH = os.path.join(BASE_DIR, 'data', 'per_game.csv')
STANDINGS_DATA_PATH = os.path.join(BASE_DIR, 'data', 'standings.csv')

# 전역 데이터 변수
player_data_df = None
standings_data_df = None
player_list = [] # 선수 이름 리스트
team_abbr_map = {
    'Atlanta Hawks': 'ATL', 'Boston Celtics': 'BOS', 'Brooklyn Nets': 'BRK',
    'Charlotte Hornets': 'CHO', 'Chicago Bulls': 'CHI', 'Cleveland Cavaliers': 'CLE',
    'Dallas Mavericks': 'DAL', 'Denver Nuggets': 'DEN', 'Detroit Pistons': 'DET',
    'Golden State Warriors': 'GSW', 'Houston Rockets': 'HOU', 'Indiana Pacers': 'IND',
    'LA Clippers': 'LAC', 'Los Angeles Lakers': 'LAL', 'Memphis Grizzlies': 'MEM',
    'Miami Heat': 'MIA', 'Milwaukee Bucks': 'MIL', 'Minnesota Timberwolves': 'MIN',
    'New Orleans Pelicans': 'NOP', 'New York Knicks': 'NYK', 'Oklahoma City Thunder': 'OKC',
    'Orlando Magic': 'ORL', 'Philadelphia 76ers': 'PHI', 'Phoenix Suns': 'PHO',
    'Portland Trail Blazers': 'POR', 'Sacramento Kings': 'SAC', 'San Antonio Spurs': 'SAS',
    'Toronto Raptors': 'TOR', 'Utah Jazz': 'UTA', 'Washington Wizards': 'WAS'
}

# ----------------------------------------------------------------------
# 2. 데이터 로딩 함수 (백그라운드 스레드)
# ----------------------------------------------------------------------

def load_data():
    """CSV 파일을 읽어와 전역 데이터프레임을 채우는 함수."""
    global player_data_df, standings_data_df, player_list
    print("⏳ 데이터 로딩 스레드 시작...")
    
    try:
        # 선수 데이터 로드
        player_data_df = pd.read_csv(PLAYER_DATA_PATH)
        player_data_df = player_data_df.rename(columns={'Player': 'Player', 'Tm': 'Team'})
        player_data_df = player_data_df.fillna(0)
        player_list = sorted(player_data_df['Player'].unique().tolist())
        
        print(f"✅ 선수 데이터 로드 완료: {len(player_data_df)} 행")

        # 팀 순위 데이터 로드
        standings_data_df = pd.read_csv(STANDINGS_DATA_PATH)
        standings_data_df = standings_data_df.rename(columns={'Team Name': 'Team'})
        standings_data_df['Team Abbr'] = standings_data_df['Team'].map(team_abbr_map).fillna(standings_data_df['Team'])
        print(f"✅ 순위 데이터 로드 완료: {len(standings_data_df)} 행")

        print("🎉 모든 데이터 로드 및 전처리 완료.")
        
    except FileNotFoundError as e:
        print(f"❌ 데이터 파일을 찾을 수 없어, 명단 및 검색 기능을 사용할 수 없습니다. 오류: {e}")
    except Exception as e:
        print(f"❌ 데이터 로딩 중 예상치 못한 오류 발생: {e}")

# 서버 시작 시 데이터 로드를 백그라운드 스레드로 실행
data_thread = threading.Thread(target=load_data)
data_thread.daemon = True 
data_thread.start()

# ----------------------------------------------------------------------
# 3. 데이터 분석 및 질의응답 로직
# ----------------------------------------------------------------------

# 선수 스탯 검색 (캐싱 적용)
@lru_cache(maxsize=128)
def search_player_stats(player_name, season):
    """특정 시즌의 특정 선수의 주요 기록을 조회합니다."""
    if player_data_df is None:
        return None
    
    df_player = player_data_df[
        (player_data_df['Player'].str.contains(player_name, case=False, na=False)) & 
        (player_data_df['Season'] == season)
    ]
    
    if df_player.empty:
        return None
    
    df_player = df_player.sort_values(by='G', ascending=False).iloc[0]
    
    stats_to_show = ['G', 'MP', 'FG%', 'TRB', 'AST', 'STL', 'BLK', 'PTS']
    result = {
        'Player': df_player['Player'],
        'Team': df_player['Team'],
        'Season': df_player['Season'],
    }
    for stat in stats_to_show:
        result[stat] = f"{df_player[stat]:.1f}" if isinstance(df_player[stat], (float, np.floating)) else str(df_player[stat])
        
    return result

# 특정 스탯 순위 검색 (캐싱 적용)
@lru_cache(maxsize=128)
def search_top_players(season, stat, top_n=3):
    """특정 시즌의 특정 스탯에서 상위 N명의 선수를 조회합니다."""
    if player_data_df is None:
        return None
    
    min_games = player_data_df[player_data_df['Season'] == season]['G'].max() * 0.5
    
    df_season = player_data_df[
        (player_data_df['Season'] == season) & 
        (player_data_df['G'] >= min_games)
    ].copy()
    
    if stat not in df_season.columns:
        return None
    
    df_top = df_season.sort_values(by=stat, ascending=False).head(top_n)
    
    results = []
    for _, row in df_top.iterrows():
        results.append({
            'rank': len(results) + 1,
            'player': row['Player'],
            'team': row['Team'],
            'stat_value': f"{row[stat]:.2f}",
            'stat_name': stat
        })
        
    return results

# 선수 개인 순위 검색 (캐싱 적용)
@lru_cache(maxsize=128)
def search_player_rank(player_name, season, stat):
    """특정 선수가 특정 시즌의 특정 스탯에서 몇 위인지 조회합니다."""
    if player_data_df is None:
        return None
    
    min_games = player_data_df[player_data_df['Season'] == season]['G'].max() * 0.5
    
    df_filtered = player_data_df[
        (player_data_df['Season'] == season) & 
        (player_data_df['G'] >= min_games)
    ].copy()
    
    if stat not in df_filtered.columns:
        return None
        
    df_filtered['Rank'] = df_filtered[stat].rank(method='dense', ascending=False)
    
    player_row = df_filtered[df_filtered['Player'].str.contains(player_name, case=False, na=False)]
    
    if player_row.empty:
        return None
        
    rank_info = player_row.sort_values(by='Rank').iloc[0]
    
    return {
        'player': rank_info['Player'],
        'season': season,
        'stat': stat,
        'value': f"{rank_info[stat]:.1f}",
        'rank': int(rank_info['Rank'])
    }


# 팀 순위 검색 (캐싱 적용)
@lru_cache(maxsize=128)
def search_team_standings(season, conference, rank):
    """특정 시즌의 특정 컨퍼런스에서 특정 순위의 팀을 조회합니다."""
    if standings_data_df is None:
        return None
        
    df_standings = standings_data_df[
        (standings_data_df['Season'] == season) &
        (standings_data_df['Conference'] == conference) &
        (standings_data_df['Rank'] == rank)
    ]
    
    if df_standings.empty:
        return None
        
    return {
        'season': season,
        'conference': conference,
        'rank': rank,
        'team': df_standings.iloc[0]['Team']
    }


# ----------------------------------------------------------------------
# 4. 질의응답 (Q&A) 처리 로직
# ----------------------------------------------------------------------

def handle_query(query):
    """사용자 질의를 분석하고 적절한 함수를 호출하여 답변을 생성합니다."""
    query = query.lower().strip()
    
    if player_data_df is None:
        return "데이터가 아직 로드되지 않았거나 로드에 실패했습니다. 잠시 후 다시 시도해주세요."
        
    seasons = [str(s) for s in range(2019, 2025)] 
    default_season = '2023-24'
    season = next((s for s in seasons if s in query), default_season)

    # 1. 선수 개인 스탯 순위 조회 (예: 르브론 제임스 득점 순위는?)
    stat_keywords = {'득점': 'PTS', '리바운드': 'TRB', '어시스트': 'AST', '블록': 'BLK', '스틸': 'STL'}
    for ko_stat, en_stat in stat_keywords.items():
        if f"{ko_stat} 순위" in query or f"순위 {ko_stat}" in query:
            for player in sorted(player_list, key=len, reverse=True):
                if player.lower() in query:
                    rank_result = search_player_rank(player, season, en_stat)
                    if rank_result:
                        return (f"📊 {rank_result['season']} 시즌 **{rank_result['player']}** 선수의 경기당 평균 **{ko_stat}** 기록은 "
                                f"{rank_result['value']}로, 리그 전체 **{rank_result['rank']}위**입니다. (최소 경기 출전 기준)")
                    break

    # 2. TOP N 선수 스탯 순위 조회 (예: 2023-24 시즌 리바운드 TOP 3 선수는?)
    top_n = next((int(s) for s in query.split() if s.isdigit()), 3) 
    for ko_stat, en_stat in stat_keywords.items():
        if f"top {top_n} {ko_stat}" in query or f"{ko_stat} top {top_n}" in query or f"상위 {top_n} {ko_stat}" in query:
            top_results = search_top_players(season, en_stat, top_n)
            if top_results:
                response = f"🥇 {season} 시즌 경기당 평균 **{ko_stat}** TOP {top_n} 선수 명단입니다 (최소 경기 출전 기준):\n"
                for r in top_results:
                    response += f"- **{r['rank']}위:** {r['player']} ({r['team']}) - {r['stat_value']} {ko_stat}\n"
                return response.strip()
            
    # 3. 팀 순위 조회 (예: 2022-23 시즌 동부 1위 팀은?)
    conf_keywords = {'동부': 'East', '서부': 'West'}
    rank_keywords = {f'{i}위': i for i in range(1, 16)}

    for ko_conf, en_conf in conf_keywords.items():
        for ko_rank, rank_num in rank_keywords.items():
            if f"{ko_conf} 컨퍼런스 {ko_rank}" in query or f"{ko_conf} {ko_rank} 팀" in query:
                standing_result = search_team_standings(season, en_conf, rank_num)
                if standing_result:
                    return f"🏀 {standing_result['season']} 시즌 **{ko_conf}** 컨퍼런스 **{standing_result['rank']}위** 팀은 **{standing_result['team']}** 입니다."

    # 4. 선수 주요 기록 조회 (예: 2023-24 시즌 니콜라 요키치 주요 기록은?)
    for player in sorted(player_list, key=len, reverse=True):
        if player.lower() in query:
            stats = search_player_stats(player, season)
            if stats:
                response = f"⛹️ **{stats['Player']}** 선수의 {stats['Season']} 시즌 주요 기록입니다 (평균):\n"
                response += f"- 소속팀: **{stats['Team']}**\n"
                response += f"- 득점(PTS): {stats['PTS']}\n"
                response += f"- 리바운드(TRB): {stats['TRB']}\n"
                response += f"- 어시스트(AST): {stats['AST']}\n"
                response += f"- 야투율(FG%): {stats['FG%']}%\n"
                response += f"- 출전 시간(MP): {stats['MP']}분\n"
                response += f"- 스틸(STL): {stats['STL']}, 블록(BLK): {stats['BLK']}\n"
                return response
            
    return f"🤔 죄송합니다. '{query}'에 대한 정보를 찾지 못했습니다. 질문을 좀 더 구체적으로 바꿔주시겠어요? (예: 2023-24 시즌 르브론 제임스 득점 순위는?)"

# ----------------------------------------------------------------------
# 5. Flask 라우트 및 HTML 템플릿
# ----------------------------------------------------------------------

HTML_TEMPLATE = """
<!doctype html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <title>🏀 NBA 데이터 Q&A 시스템</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: auto; background: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 6px 20px rgba(0, 0, 0, 0.1); }
        h1 { color: #004d98; text-align: center; margin-bottom: 25px; font-weight: 700; border-bottom: 3px solid #f9a01b; padding-bottom: 10px; }
        h2 { color: #f9a01b; font-size: 1.2em; margin-top: 20px; }
        .form-group { margin-bottom: 20px; }
        #query-input { width: 100%; padding: 15px; border: 2px solid #ddd; border-radius: 8px; font-size: 16px; box-sizing: border-box; transition: border-color 0.3s; }
        #query-input:focus { border-color: #004d98; outline: none; }
        #submit-btn { width: 100%; padding: 12px; background-color: #004d98; color: white; border: none; border-radius: 8px; font-size: 18px; cursor: pointer; transition: background-color 0.3s, transform 0.1s; }
        #submit-btn:hover { background-color: #003366; }
        #submit-btn:active { transform: scale(0.99); }
        #response-container { background: #e8f4fd; padding: 20px; border-radius: 8px; min-height: 100px; margin-top: 25px; border-left: 5px solid #004d98; white-space: pre-wrap; word-wrap: break-word; line-height: 1.6; }
        .example-list { list-style: none; padding: 0; margin-top: 15px; }
        .example-list li { background: #fff; margin-bottom: 8px; padding: 10px; border-radius: 6px; border: 1px solid #eee; cursor: pointer; transition: background-color 0.2s; }
        .example-list li:hover { background-color: #f0f8ff; }
        .status-message { text-align: center; margin-top: 15px; padding: 10px; border-radius: 6px; }
        .status-loading { background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
        .status-ready { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .response-intro { font-weight: bold; color: #333; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🏀 NBA 데이터 Q&A 시스템</h1>
        
        <div id="status-message" class="status-message {{ status_class }}">
            {{ status_text }}
        </div>

        <form id="qa-form">
            <div class="form-group">
                <input type="text" id="query-input" name="query" placeholder="궁금한 것을 물어보세요 (예: 르브론 제임스 득점 순위는?)" required>
            </div>
            <button type="submit" id="submit-btn">검색</button>
        </form>

        <div id="response-container">
            <div class="response-intro">응답:</div>
            {{ response|default('여기에 답변이 표시됩니다.', true) }}
        </div>

        <h2>💡 자주 묻는 질문 예시</h2>
        <ul class="example-list">
            <li onclick="document.getElementById('query-input').value='2023-24 시즌 니콜라 요키치 주요 기록은?'; document.getElementById('qa-form').requestSubmit();">2023-24 시즌 니콜라 요키치 주요 기록은?</li>
            <li onclick="document.getElementById('query-input').value='2023-24 시즌 르브론 제임스 득점 순위는?'; document.getElementById('qa-form').requestSubmit();">2023-24 시즌 르브론 제임스 득점 순위는?</li>
            <li onclick="document.getElementById('query-input').value='2022-23 시즌 동부 컨퍼런스 1위 팀은?'; document.getElementById('qa-form').requestSubmit();">2022-23 시즌 동부 컨퍼런스 1위 팀은?</li>
            <li onclick="document.getElementById('query-input').value='2023-24 시즌 리바운드 TOP 5 선수는?'; document.getElementById('qa-form').requestSubmit();">2023-24 시즌 리바운드 TOP 5 선수는?</li>
        </ul>
    </div>
    
    <script>
        document.getElementById('qa-form').addEventListener('submit', function(e) {
            e.preventDefault();
            const query = document.getElementById('query-input').value;
            const responseContainer = document.getElementById('response-container');
            // 답변 처리 중 메시지를 표시
            responseContainer.innerHTML = '<div class="response-intro">응답:</div><p>답변을 처리 중입니다... ⏳</p>';

            // /api/query 엔드포인트로 질문(query)을 POST 방식으로 전송
            fetch('/api/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ query: query })
            })
            .then(response => response.json())
            .then(data => {
                // 서버에서 받은 응답(data.response)을 HTML로 변환하여 표시
                const responseText = data.response.replace(/\n/g, '<br>'); // 줄바꿈 처리
                responseContainer.innerHTML = `<div class="response-intro">응답:</div>${responseText}`;
            })
            .catch(error => {
                responseContainer.innerHTML = '<div class="response-intro">응답:</div><p style="color: red;">오류가 발생했습니다: ' + error + '</p>';
            });
        });

        // 예시 질문 클릭 시, 입력 필드 업데이트 후 자동으로 폼 제출
        document.querySelectorAll('.example-list li').forEach(item => {
            item.addEventListener('click', function() {
                // li 태그 안의 텍스트를 query로 사용
                const query = this.textContent; 
                document.getElementById('query-input').value = query;
                document.getElementById('qa-form').dispatchEvent(new Event('submit'));
            });
        });
    </script>
</body>
</html>
"""

# 메인 페이지 라우트
@app.route('/')
def index():
    """메인 페이지 렌더링"""
    if player_data_df is None:
        status_text = "데이터 로딩 중입니다... ⏳"
        status_class = "status-loading"
    else:
        status_text = "데이터 로드 완료! 🚀 질문을 시작하세요."
        status_class = "status-ready"
        
    return render_template_string(HTML_TEMPLATE, status_text=status_text, status_class=status_class)

# API 엔드포인트
@app.route('/api/query', methods=['POST'])
def api_query():
    """질의응답 API"""
    data = request.get_json()
    query = data.get('query', '')
    
    response_text = handle_query(query)
    
    return jsonify({'response': response_text})

# 서버 실행
if __name__ == '__main__':
    print("==================================================")
    print("💡 Flask 웹 서버 시작")
    print("🔗 http://127.0.0.1:5000/")
    print("==================================================")
    app.run(debug=True)