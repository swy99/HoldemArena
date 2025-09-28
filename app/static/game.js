let NUM_PLAYERS = 8;
let seats = null;
let bb = 2;
let minraiseby = 2;
let maxbet = 2;
let tocall = 0;
let mychips = 0;
let pot = 0;
let raise_values = [];
let active_idx = [];
let previousBets = {};
let firstRender = true;
let state = null;
let action_count = null;
let timerInterval = null;
let game_ended = false;

const minHeight = 24;             // 손잡이만 보일 최소 높이
const snapHeight = 230;           // 버튼들이 간신히 보이는 위치
const maxHeight = window.innerHeight - 200;            // 정보바 아래쪽 제한선

setup_positions(NUM_PLAYERS);

/* ========== network part ============ */

const token = localStorage.getItem("holdemarena_token");
const game_id = localStorage.getItem("holdemarena_game_id");
const player_id = localStorage.getItem("holdemarena_player_id");
const hostname = localStorage.getItem("holdemarena_hostname");

let socket = createNewSocket();

function action(amount) {
    socket.send(JSON.stringify({
        type: "action",
        amount: amount,
        action_count: action_count
    }));
}


function renderState(payload) {
    action_count = payload.action_count;
    let prevstate = state;
    state = payload;
    let isfirstTurn = payload.stage === "Preflop";
    let sbfound = false, bbfound = false;
    for (let p of payload.players){
        switch(p.bet){
            case payload.sb:
                if (sbfound) isfirstTurn = false;
                else sbfound = true;
                break;
            case payload.bb:
                if (bbfound) isfirstTurn = false;
                else bbfound = true;
                break;
            case 0:
                break;
            default:
                isfirstTurn = false;
                break;
        }
        if (p.folded) isfirstTurn = false;
    }
    isfirstTurn = isfirstTurn && (sbfound && bbfound);
    const mustDryRender = prevstate === null && !isfirstTurn;
    if (mustDryRender || isfirstTurn){
        initCCards();
        initPCards();
    }

    maxbet = 0;
    tocall = 0;
    mychips = 0;
    active_idx = [];
    for(let id of ["SB", "BB", "D"]){
        const el = document.getElementById(id);
        if (el) {
            el.remove();
        }
    }

    //stage
    //turn
    document.getElementById("info_big").innerText = `${payload.stage} - ${payload.turn}`;
    document.getElementById("info_small").innerText = `Blinds: 🪙${payload.sb}/🪙${payload.bb}`;
    if(payload.turn === player_id){
        document.getElementById("action_control").classList.remove("hidden");
        document.getElementById('action_control').style.height = `${snapHeight}px`;
        document.querySelector(".bg-tertiary").classList.add("table-info-pulse");
    }
    else{
        document.getElementById("action_control").classList.add("hidden");
        document.querySelector(".bg-tertiary").classList.remove("table-info-pulse");
    }
    updateExpandButtonVisibility();
    //sb, bb, minraiseby
    bb = payload.bb;
    minraiseby = payload.minraiseby;
    //board
    let board = payload.board;
    
    for(let i=0;i<board.length;i++){
        if (mustDryRender){
            setCardDry(`cc${i+1}`, board[i]);
        }
        else{
            if (i < prevstate.board.length){
                ;
            } 
            else{
                requestCardMotion("deal", `cc${i+1}`, board[i]);
            }
        }
    }
    
    NUM_PLAYERS = payload.players.length;
    setup_positions(NUM_PLAYERS);
    pot = 0;
    for(const p of payload.players){
        pot += p.bet;
    }
    document.getElementById("pot").innerText = `Pot: 🪙${parseInt(pot).toLocaleString()}`;
    
    function rotateListByPid(l, target) {
        const index = l.findIndex(item => item.pid === target);
        if (index === -1) {
            return l;
        }
        return l.slice(index).concat(l.slice(0, index));
    }

    for(let i=0;i<NUM_PLAYERS;i++){
        let p = payload.players[i];
        p.dealingidx = i;
    }
    
    let rotated = rotateListByPid(payload.players, player_id);
    let prevrotated = prevstate === null ? null : rotateListByPid(prevstate.players, player_id);
    let mybet = 0;
    if (isfirstTurn){
        for (let dealingidx=0; dealingidx<NUM_PLAYERS; dealingidx++){
            for (let k=0; k<NUM_PLAYERS; k++){
                const p = rotated[k];
                if ((dealingidx == p.dealingidx)){
                    let i = seats[k];
                    for (let j=1; j<3; j++){
                        requestCardMotion("deal", `p${i}c${j}`, p.hole_cards[j-1]);
                    }
                }
            }
        }
    }
    for(let idx=0;idx<NUM_PLAYERS;idx++){
        let prevplayer = prevstate == null ? null : prevrotated[idx];
        let player = rotated[idx];
        let i = seats[idx];
        //pid, turn
        if(payload.turn === player.pid){
            document.getElementById(`p${i}_name`).innerText = (player_id === player.pid ? `You (${player.pid})` : player.pid);
            //document.getElementById(`p${i}_name`).classList.add("font-extrabold");
            document.getElementById(`player${i}`).classList.add("pulse-outline");
        }
        else{
            document.getElementById(`p${i}_name`).innerText = (player_id === player.pid ? `You (${player.pid})` : player.pid);
            //document.getElementById(`p${i}_name`).classList.remove("font-extrabold");
            document.getElementById(`player${i}`).classList.remove("pulse-outline");
        }
        //position
        switch(player.position){
            case "SB":
            document.getElementById(`p${i}_chips`).insertAdjacentHTML('afterend', 
                '<div id="SB" class="absolute -top-1 -left-1 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">SB</div>');
            break;
            case "BB":
            document.getElementById(`p${i}_chips`).insertAdjacentHTML('afterend', 
                '<div id="BB" class="absolute -top-1 -left-1 bg-blue-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">BB</div>');
            break;
            default:
            break;
        }
        //hole_cards
        for(let j=1;j<3;j++){
            let card = player.hole_cards[j-1];
            let prevcard = prevplayer == null ? null : prevplayer.hole_cards[j-1];
            if (mustDryRender){
                setCardDry(`p${i}c${j}`, card);
            }
            else if (!mustDryRender && !isfirstTurn){
                if (card !== prevcard){
                    requestCardMotion("open", `p${i}c${j}`, card);
                }
            }
        }
        //folded
        if(player.folded) document.getElementById(`p${i}_hand`).classList.add("opacity-50");
        else document.getElementById(`p${i}_hand`).classList.remove("opacity-50");
        //chips
        document.getElementById(`p${i}_chips`).innerText = `🪙${parseInt(player.chips).toLocaleString()}`;
        mychips = player_id === player.pid ? player.chips : mychips;
        //bet sound effect
        const pid = player.pid;
        const prevBet = previousBets[pid] ?? 0;
        const currentBet = player.bet ?? 0;
        if (!firstRender && currentBet > prevBet) {// 처음 렌더링은 사운드 생략
            playSound("sfx_chips");
        }
        previousBets[pid] = currentBet;
        //bet
        document.getElementById(`p${i}_bets`).innerText = `🪙${parseInt(player.bet).toLocaleString()}`;
        maxbet = player.bet > maxbet ? player.bet : maxbet;
        if(player_id === player.pid){
            mybet = player.bet;
        }
        //timebank
        document.getElementById(`p${i}_bank`).innerText = "⏱️" + formatSeconds(player.timebank ?? 0);
    }
    firstRender = false;
    
    // D
    if (active_idx.length > 2)
        document.getElementById(`p${seats[active_idx[active_idx.length - 1]]}_chips`).insertAdjacentHTML('afterend', 
            '<div id="D" class="dealer-button absolute -top-2 -right-2 w-5 h-5 rounded-full bg-white text-xs flex items-center justify-center font-bold">D</div>');
    
    if(payload.turn === player_id){
        tocall = maxbet - mybet;
        let minraise = minraiseby + maxbet;
        let minbettoraise = minraise - mybet;
        
        document.getElementById("min_raise_value").innerText = `🪙${minbettoraise.toLocaleString()}`;
        document.getElementById("all_in_value").innerText = `🪙${mychips.toLocaleString()}`;

        document.getElementById("fold_button").disabled = false;
        document.getElementById("call_button").disabled = false;
        document.getElementById("call_button").classList.remove("bg-gray-300");
        document.getElementById("call_button").classList.add("bg-green-500");
        document.getElementById("raise_button").disabled = false;
        document.getElementById("raise_button").classList.remove("bg-gray-300");
        document.getElementById("raise_button").classList.add("bg-blue-500");
        if(tocall === 0){ // checkable
            document.getElementById("fold_button").innerText = "Check";
            document.getElementById("fold_button").classList.remove("bg-red-500");
            document.getElementById("fold_button").classList.add("bg-yellow-500");
            
            document.getElementById("call_button").disabled = true;
            document.getElementById("call_button").classList.remove("bg-green-500");
            document.getElementById("call_button").classList.add("bg-gray-300");
        }
        else{ // foldable
            document.getElementById("fold_button").innerText = "Fold";
            document.getElementById("fold_button").classList.add("bg-red-500");
            document.getElementById("fold_button").classList.remove("bg-yellow-500");
        }
        if(tocall > mychips){ // all-in call
            document.getElementById("call_button").innerText = "All-in\n🪙" + parseInt(mychips).toLocaleString();
        }
        else{
            document.getElementById("call_button").innerText = "Call🪙" + parseInt(tocall).toLocaleString();
        }
        if(minbettoraise > mychips){ // not raisable
            document.getElementById("raise_button").disabled = true;
            document.getElementById("raise_button").classList.remove("bg-blue-500");
            document.getElementById("raise_button").classList.add("bg-gray-300");
        }
        else{ // raisable
            document.getElementById("bet_value").value = minbettoraise;
            document.getElementById("raise_button").innerText = tocall > 0 ? "Raise" : "Bet";
        }
        
        raise_values = getBetSliderValues({
            pot: pot,
            bb: bb,
            minRaise: minbettoraise,
            stack: mychips
        });
        const slider = document.getElementById("bet_slider");
        slider.min = 0;
        slider.max = raise_values.length - 1;
        slider.step = 1;
        slider.value = 0;
        
        slider.addEventListener("input", () => {
            const bet = raise_values[slider.value];
            document.getElementById("bet_value").value = bet;
            document.getElementById("raise_button").innerText = (tocall > 0 ? "Raise" : "Bet") + " 🪙" + bet.toLocaleString();
        });
        slider.dispatchEvent(new Event("input"));
        
        document.getElementById("bet_value").addEventListener("input", () => {
        const bet = parseInt(document.getElementById("bet_value").value);
        if (!isNaN(bet)) {
            document.getElementById("raise_button").innerText = (tocall > 0 ? "Raise" : "Bet") + " 🪙" + bet.toLocaleString();
        }
});
    }

    if (timerInterval) clearInterval(timerInterval);

    const currentPlayer = payload.players.find(p => p.pid === payload.turn);
    if (currentPlayer) {
        const remaining = parseFloat(currentPlayer.remaining_time) || 0;
        const timebank = parseFloat(currentPlayer.timebank) || 0;

        let seatIndex = null;
        for (let idx = 0; idx < rotated.length; idx++) {
            if (rotated[idx].pid === payload.turn) {
                seatIndex = seats[idx];
                break;
            }
        }

        const bankEl = document.getElementById(`p${seatIndex}_bank`);
        const progress = document.querySelector(".timer-progress");

        let start = Date.now();

        timerInterval = setInterval(() => {
            const elapsed = (Date.now() - start) / 1000;
            let percent = 0;

            if (elapsed < remaining) {
                percent = ((remaining - elapsed) / 15) * 100;
                progress.classList.add("bg-blue-500");
                progress.classList.remove("bg-red-500");

                // 여긴 timebank가 줄어들지 않음 → 그대로 표시
                if (bankEl) bankEl.innerText = "⏱️" + formatSeconds(timebank);
            }
            else if (elapsed < remaining + timebank) {
                const timebankUsed = elapsed - remaining;
                const liveTimebank = Math.max(0, timebank - timebankUsed);
                percent = (liveTimebank / timebank) * 100;

                progress.classList.remove("bg-blue-500");
                progress.classList.add("bg-red-500");

                if (bankEl) bankEl.innerText = "⏱️" + formatSeconds(liveTimebank);
            }
            else {
                percent = 0;
                if (bankEl) bankEl.innerText = "⏱️" + formatSeconds(0);
                clearInterval(timerInterval);
            }

            progress.style.width = `${Math.max(0, percent)}%`;
        }, 17);
    }
}

function renderResult(payload) {
    if (timerInterval) clearInterval(timerInterval);
    const progress = document.querySelector(".timer-progress");
    progress.style.width = "0%";
    progress.classList.remove("bg-blue-500", "bg-red-500");

    document.getElementById("info_big").innerText = `Hand Result`;
    document.getElementById("pot").innerText = '🔥Result🔥';
    document.getElementById("action_control").classList.remove("hidden");
    document.querySelector(".bg-tertiary").classList.remove("table-info-pulse");
    updateExpandButtonVisibility();
    //board
    let prevstate = state;
    let board = payload.board;
    for(let i=0;i<board.length;i++){
        if (i < prevstate.board.length){
            ;
        } 
        else{
            requestCardMotion("deal", `cc${i+1}`, board[i]);
        }
    }

    NUM_PLAYERS = payload.players.length;
    setup_positions(NUM_PLAYERS);
    
    function rotateListByPid(l, target) {
        const index = l.findIndex(item => item.pid === target);
        if (index === -1) {
            return l;
        }
        return l.slice(index).concat(l.slice(0, index));
    }
    
    let rotated = rotateListByPid(payload.players, player_id);
    let prevrotated = prevstate == null ? null : rotateListByPid(prevstate.players, player_id);
    for(let idx=0;idx<NUM_PLAYERS;idx++){
        let player = rotated[idx];
        let prevplayer = prevrotated == null ? null : prevrotated[idx];
        let i = seats[idx];
        //pid
        document.getElementById(`p${i}_name`).innerText = (player_id === player.pid ? `You (${player.pid})` : player.pid);
        document.getElementById(`player${i}`).classList.remove("pulse-outline");
        //hole_cards
        for(let j=1;j<3;j++){
            let card = player.hole_cards[j-1];
            let prevcard = prevplayer == null ? null : prevplayer.hole_cards[j-1];
            if (card !== prevcard){
                requestCardMotion("open", `p${i}c${j}`, card);
            }
        }
        //chips
        document.getElementById(`p${i}_chips`).innerText = `🪙${parseInt(player.chips).toLocaleString()}`;
        mychips = player_id === player.pid ? player.chips : mychips;
        //change

        //payout
        document.getElementById(`p${i}_bets`).innerText = `+🪙${parseInt(player.payout).toLocaleString()}`;
        //hand
        document.getElementById(`p${i}_bank`).innerText = player.hand === "???" ? "" : player.hand;
    }
    document.getElementById("action_control").classList.add("hidden");
    updateExpandButtonVisibility();
}














/* ================== DOM control ================== */

document.addEventListener('DOMContentLoaded', function() {
    // Timer animation with time bank
    const timerProgress = document.querySelector('.timer-progress');
    let width = 100;
    let normalTime = 30; // 30 seconds normal time
    let currentTime = normalTime;
    // setInterval(function() {
    //     width = (currentTime / (isUsingTimeBank ? timeBank : normalTime)) * 100;
    //     timerProgress.style.width = width + '%';
    //     currentTime -= 0.1;
    // }, 100);


    // Card hover effect
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => {
        card.addEventListener('touchstart', function() {
            this.style.transform = 'translateY(-5px)';
        });
        card.addEventListener('touchend', function() {
            this.style.transform = 'translateY(0)';
        });
    });


    
    // JS: 슬라이더 이벤트에 연결
    const slider = document.getElementById("bet_slider");
    slider.addEventListener("input", () => {
        const val = raise_values[slider.value];
        slider.setAttribute("data-value", `🪙${val}`);
    });
        
    document.getElementById("bet_value").addEventListener("input", () => {
        const v = parseInt(document.getElementById("bet_value").value);
        if (!isNaN(v)) {
            const closestIdx = raise_values.reduce((prevIdx, currVal, idx) =>
            Math.abs(currVal - v) < Math.abs(raise_values[prevIdx] - v) ? idx : prevIdx, 0);
            slider.value = closestIdx;
        }
    });
    // draghandler 추가
    add_drag_handlers();

    // action control 오픈 버튼
    const actionControl = document.getElementById("action_control");
    const expandButton = document.getElementById("expand_button");
    expandButton.addEventListener("click", () => {
        actionControl.style.height = `${snapHeight}px`;
        updateExpandButtonVisibility();
    });
        
    // 각 버튼에 클릭 사운드 추가
    document.getElementById("fold_button").addEventListener("click", () => playSound("sfx_click"));
    document.getElementById("call_button").addEventListener("click", () => playSound("sfx_click"));
    document.getElementById("raise_button").addEventListener("click", () => playSound("sfx_click"));

    // popstate는 뒤로가기를 눌렀을 때 발생
    history.pushState(null, "", location.href);
    window.addEventListener("popstate", function (event) {
        exit();
        // 다시 현재 페이지 상태를 push하여 뒤로가기를 무효화
        history.pushState(null, "", location.href);
    });
});


function setup_positions(num_players){
    seats = [
        null, null,
        [1,5],
        [1,4,6],
        [1,3,5,7],
        [1,3,4,6,7],
        [1,3,4,5,6,7],
        [1,2,3,4,6,7,8],
        [1,2,3,4,5,6,7,8]
    ][num_players];
    for(let i=1;i<9;i++){
        if(seats.includes(i)){
            document.getElementById(`player${i}`).classList.remove("invisible");
        }
        else{
            document.getElementById(`player${i}`).classList.add("invisible");
        }
    }
}

function showRanking(rankings) {
    document.getElementById("rankingOverlay").classList.remove("hidden");
    container = document.getElementById("rankings");
    container.innerHTML = "";

    const entries = Object.entries(rankings);
    entries.sort((a, b) => a[1] - b[1]); // 순위 오름차순 정렬
    
    for (const [user, rank] of entries) {
        if (user === player_id) {
            const suffixes = {
                1: "st",
                2: "nd",
                3: "rd"
            };
            const suffix = suffixes[rank] || "th";
            document.getElementById("pot").innerText = String(rank) + suffixes[rank];
        }
        const li = document.createElement('li');
        li.className = 'flex justify-between border-b pb-1';

        const spanLeft = document.createElement('span');
        spanLeft.className = 'font-medium';
        spanLeft.textContent = `${rank}. ${user}`;

        const spanRight = document.createElement('span');
        spanRight.className = 'text-primary font-bold';
        spanRight.textContent = ` `;

        li.appendChild(spanLeft);
        li.appendChild(spanRight);

        container.appendChild(li);
    }
}

function closeRanking() {
    document.getElementById("rankingOverlay").classList.add("hidden");
}



/* =============== Helper Functions =================== */

function call(){
    action(tocall > mychips ? mychips : tocall);
}

function raise(){
    let value = document.getElementById("bet_value").value;
    action(parseInt(value));
}

function refresh() {
    // 이미 닫혀 있거나 닫히는 중이면 바로 새로 연결
    if (!socket || socket.readyState === WebSocket.CLOSED || socket.readyState === WebSocket.CLOSING) {
        socket = createNewSocket();
        return;
    }
    
    try {
        // 소켓 닫고, 완전히 닫히면 새로 연결
        socket.addEventListener('close', () => {
            socket = createNewSocket();
        }, { once: true });
        socket.close();
    } catch (e) {
        console.error("소켓 닫기 실패:", e);
        // 실패 시에도 새로 연결 시도
        socket = createNewSocket();
    }
}

function exit(){
    if (game_ended) {
        window.history.back();
        return
    }
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 z-[80] flex items-center justify-center';
    modal.innerHTML = `
<div class="absolute inset-0 bg-black/50 backdrop-blur-sm"></div>
<div class="relative bg-white rounded-lg p-6 w-5/6 max-w-md">
    <div class="text-center mb-6">
    <div class="w-16 h-16 mx-auto bg-primary/10 rounded-full flex items-center justify-center mb-4">
        <i class="ri-logout-box-line ri-2x text-primary"></i>
    </div>
    <h3 class="text-xl font-bold mb-2">Confirm Exit</h3>
    <p class="text-sm text-gray-600">Are you sure you want to quit? You may receive a penalty for leaving early.</p>
    </div>
    <div class="flex space-x-3">
    <button class="flex-1 py-3 border border-gray-200 rounded-button text-gray-700 hover:bg-gray-50 transition-colors" id="cancelExit">Cancel</button>
    <button class="flex-1 py-3 bg-red-500 text-white rounded-button hover:bg-red-500/90 transition-colors" id="confirmExit">Leave</button>
    </div>
</div>
`;
    
    document.body.appendChild(modal);
    
    const cancelButton = modal.querySelector('#cancelExit');
    const confirmButton = modal.querySelector('#confirmExit');
    
    modal.addEventListener('click', (e) => {
        if (e.target === modal.querySelector('.absolute')) {
            window.history.back();
            document.body.removeChild(modal);
        }
    });
    
    cancelButton.addEventListener('click', () => {
        window.history.back();
        document.body.removeChild(modal);
    });
    
    confirmButton.addEventListener('click', () => {
        window.history.back();
        window.history.back();
    });
}

function createNewSocket() {
    const ws = new WebSocket(`wss://${location.hostname}/quick_play_ws?token=${token}`);
    ws.onopen = () => {
        console.log("✅ WebSocket 연결됨");
    };
    
    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        console.log("📩", msg);
        if (msg.type === "state_update") {
            renderState(msg.payload);
        }
        else if (msg.type === "round_result") {
            renderResult(msg.payload);
        }
        else if (msg.type === "game_end") {
            game_ended = true;
            setTimeout(() => {
                showRanking(msg.payload.rankings);
            }, 3000);
        }
    };
    ws.onerror = (err) => console.error("❌ WebSocket 에러:", err);
    ws.onclose = (event) => {
        console.warn("⚠️ WebSocket 연결 종료됨");
        if (event.code === 1006) {
            location.href = "/";
        }
    }
    return ws;
}

function getBetSliderValues({pot, bb, minRaise, stack}) {
    const values = new Set();
    
    const maxBet = stack;
    
    const potMultipliers = [0.33, 0.5, 1, 1.5, 2];
    const bbMultipliers = [1, 2, 3, 5, 10, 20, 50, 100];
    
    potMultipliers.forEach(mult => {
        const v = Math.round(pot * mult);
        if (v >= minRaise && v <= maxBet) values.add(v);
    });
    
    bbMultipliers.forEach(mult => {
        const v = Math.round(bb * mult);
        if (v >= minRaise && v <= maxBet) values.add(v);
    });
    
    values.add(minRaise);
    values.add(maxBet);
    
    return Array.from(values).sort((a, b) => a - b);
}

function playSound(id) {
    const audio = document.getElementById(id);
    if (audio) {
        audio.currentTime = 0;
        audio.play().catch(e => {
            console.warn("⚠️ 사운드 재생 실패:", e);
        });
    }
}

function formatSeconds(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}

function add_drag_handlers() {
    const actionControl = document.getElementById('action_control');
    const dragHandle = document.getElementById('dragHandle');

    let isDragging = false;
    let startY = 0;
    let startHeight = 0;

    dragHandle.addEventListener('mousedown', startDrag);
    dragHandle.addEventListener('touchstart', startDrag, { passive: false });

    document.addEventListener('mousemove', onDrag);
    document.addEventListener('touchmove', onDrag, { passive: false });

    document.addEventListener('mouseup', endDrag);
    document.addEventListener('touchend', endDrag);

    // ✅ 더블탭/더블클릭으로 상태 전환
    dragHandle.addEventListener('dblclick', toggleDrawer);
    dragHandle.addEventListener('pointerdown', handleDoubleTap);

    let lastTapTime = 0;
    function handleDoubleTap(e) {
        const now = Date.now();
        if (now - lastTapTime < 300) {
            e.preventDefault();
            toggleDrawer();
        }
        lastTapTime = now;
    }
        function toggleDrawer() {
        const currentHeight = parseInt(window.getComputedStyle(actionControl).height);

        if (currentHeight <= minHeight + 10) {
            return;
            // 닫혀 있으면 → 열기
            actionControl.style.transition = 'height 0.3s ease';
            actionControl.style.height = `${snapHeight}px`;
            updateExpandButtonVisibility();
        } else if (currentHeight > snapHeight + 30) {
            // 너무 많이 열려 있으면 → 줄이기
            actionControl.style.transition = 'height 0.3s ease';
            actionControl.style.height = `${snapHeight}px`;
            updateExpandButtonVisibility();
        } else {
            // 적당히 열려 있으면 → 닫기
            actionControl.style.transition = 'height 0.3s ease';
            actionControl.style.height = `${minHeight}px`;
            updateExpandButtonVisibility();
        }
    }

    function startDrag(e) {
        isDragging = true;
        startY = e.type === 'mousedown' ? e.clientY : e.touches[0].clientY;
        const currentHeight = parseInt(window.getComputedStyle(actionControl).height);
        startHeight = isNaN(currentHeight) ? snapHeight : currentHeight;
        actionControl.style.transition = 'none';
    }

    function onDrag(e) {
        if (!isDragging) return;
        e.preventDefault();

        const currentY = e.type === 'mousemove' ? e.clientY : e.touches[0].clientY;
        const deltaY = startY - currentY; // 위로 당기면 양수

        let newHeight = startHeight + deltaY;
        newHeight = Math.max(minHeight, Math.min(maxHeight, newHeight));

        actionControl.style.height = `${newHeight}px`;
        updateExpandButtonVisibility();
    }

    function endDrag() {
        if (!isDragging) return;
        isDragging = false;
        actionControl.style.transition = 'height 0.25s ease';

        const currentHeight = parseInt(actionControl.style.height);

        if (currentHeight < (snapHeight + minHeight) / 2) {
            actionControl.style.height = `${minHeight}px`;     // 완전 닫기
            updateExpandButtonVisibility();
        } else if (currentHeight < snapHeight * 2) {
            actionControl.style.height = `${snapHeight}px`;    // 중간 스냅
            updateExpandButtonVisibility();
        } else {
            ;//actionControl.style.height = `${maxHeight}px`;     // 완전 열기
            updateExpandButtonVisibility();
        }
    }
}

function updateExpandButtonVisibility() {
    const actionControl = document.getElementById("action_control");
    const expandButton = document.getElementById("expand_button");
    
    const isHidden = actionControl.classList.contains("hidden");
    const currentHeight = parseInt(actionControl.style.height);
    if (!isHidden && currentHeight <= minHeight) {
        expandButton.classList.remove("hidden");
    } else {
        expandButton.classList.add("hidden");
    }
}
