// Friend chat

let chatSocket = null;
const token = localStorage.getItem("holdemarena_token");

let currentChatFriendUid = null;
let chatMessages = [];
let oldestTimestamp = null;
let isLoading = false;
let unreadFlags = {};
let isChatOpen = false;
let pendingFriendRequests = []; // 받은 요청 큐
let hasPendingFriendRequest = false;

let friends = []; // 전체 친구 목록
let onlineStatus = {}; // uid -> true/false
let friendsLoaded = false; // ✅ 친구 목록이 로딩 완료되었는지
let pendingStatusUpdates = []; // ✅ 친구 목록 로딩 전에 받은 presence 업데이트 저장



const pendingPartyInvites = []; // 초대 큐
const pendingPartyInviteLeaders = new Set(); // 중복 초대 방지용
let hasPendingInviteRequest = false;

let queueSocket = null;
let isConnectedtoQueueSocket = false;
let reconnectTimer = null;
let reconnectCount = 0;
let uidToName = {};
let isQueueing = false;



document.addEventListener("DOMContentLoaded", () => {
    // check if the user belongs to an ongoing game
    check_unfinished_game();

    // ✅ WebSocket 연결
    initChatSocket();
    
    // ✅ 친구 목록 불러오기
    fetchFriends();
    
    // ✅ 친구 요청 목록 불러오기
    fetchFriendRequests(); 
    
    // ✅ 내 username 불러오기
    fetchUsername();
    
    // ✅ 채팅 보내기 버튼 이벤트 연결
    const sendButton = document.getElementById("send-chat-button");
    const inputBox = document.getElementById("chat-input");
    
    sendButton.addEventListener("click", () => {
        const content = inputBox.value.trim();
        if (!content) return;
        if (!currentChatFriendUid) {
            alert("대화할 친구를 선택하세요.");
            return;
        }
        sendMessageToFriend(currentChatFriendUid, content);
        inputBox.value = "";
    });
    inputBox.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            sendButton.click();  // ✅ 클릭 대신 실행
        }
    });
    document.getElementById("chatScrollWrapper").addEventListener("scroll", () => {
        const wrapper = document.getElementById("chatScrollWrapper");
        if (wrapper.scrollTop === 0 && currentChatFriendUid) {
            loadOlderMessages(currentChatFriendUid);
        }
    });
});

function initChatSocket() {
    chatSocket = new WebSocket(`wss://${location.hostname}/chat_ws?token=${token}`);
    
    chatSocket.onopen = () => {
        console.log("✅ Chat WebSocket 연결됨");
    };
    
    chatSocket.onmessage = async (event) => {
        const msg = JSON.parse(event.data);
        console.log("📩 채팅 수신:", msg);
        
        const myUid = localStorage.getItem("holdemarena_uid");
        
        if (msg.type === "party_invite") {
            if (pendingPartyInviteLeaders.has(msg.leader_uid)) return;
            pendingPartyInviteLeaders.add(msg.leader_uid);
            pendingPartyInvites.push({ leader_uid: msg.leader_uid, from_username: msg.from_username });
            hasPendingInviteRequest = true;
            renderNextPartyInvite();
            updateGlobalFriendIndicator();
        }
        
        if (msg.type === "friend_online" || msg.type === "friend_offline") {
            if (msg.uid === myUid) {
                onlineStatus[myUid] = (msg.type === "friend_online");
                renderFriendList();
                return;
            }
            onlineStatus[msg.uid] = (msg.type === "friend_online");
            renderFriendList();
            return;
        }
        
        else if (msg.type === "friend_chat") {
            if (msg.from === myUid) {
                renderIncomingMessage(msg);
                return;
            }
            
            if (msg.from === currentChatFriendUid && isChatOpen) {
                renderIncomingMessage(msg);
                try {
                    await fetch(`https://${location.hostname}/api/mark_read`, {
                        method: "POST",
                        headers: {
                            "Authorization": "Bearer " + localStorage.getItem("holdemarena_token"),
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({ friend_uid: msg.from })
                    });
                    
                    delete unreadFlags[msg.from];
                    await fetchFriends();
                    renderFriendList();
                } catch (e) {
                    console.error("실시간 읽음 처리 실패", e);
                }
                return;
            }
            
            unreadFlags[msg.from] = true;
            renderFriendList();
            renderIncomingMessage(msg);
        }
        
        else if (msg.type === "friend_request") {
            // 받은 요청 msg: { uid, username }
            pendingFriendRequests.push(msg); // 전역 배열에 저장
            hasPendingFriendRequest = true;
            renderFriendRequest();           // UI 렌더링
            updateGlobalFriendIndicator();
        }
        
        else if (msg.type === "friend_accepted") {
            console.log("✅ 친구 요청 수락됨:", msg.uid);
            
            // 서버에서 최신 친구 목록 받아오기
            await fetchFriends();   // 이미 존재하는 함수
            renderFriendList();     // 갱신된 목록 UI 반영
        }
        
    };
    
    chatSocket.onclose = () => {
        console.log("❌ Chat WebSocket 연결 끊김");
    };
}


function renderFriendRequest() {
    const container = document.querySelector("#sideNav .bg-primary\\/5");
    if (!container) return;
    
    if (pendingFriendRequests.length === 0) {
        container.innerHTML = "";
        return;
    }
    
    const req = pendingFriendRequests[0];
    container.innerHTML = `
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center">
                    <i class="ri-user-add-line text-primary"></i>
                </div>
                <div>
                    <p class="text-sm text-black font-medium">${req.username}</p>
                    <p class="text-xs text-gray-500">wants to be friends</p>
                </div>
            </div>
            <div class="flex items-center gap-2">
                <button class="w-7 h-7 bg-green-500 text-white rounded-full flex items-center justify-center hover:bg-green-600 transition-colors"
                        onclick="respondFriendRequest('${req.uid}', true)">
                    <i class="ri-check-line"></i>
                </button>
                <button class="w-7 h-7 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors"
                        onclick="respondFriendRequest('${req.uid}', false)">
                    <i class="ri-close-line"></i>
                </button>
            </div>
        </div>
    `;
}

async function respondFriendRequest(uid, accept) {
    try {
        const res = await fetch(`https://${location.hostname}/api/respond_friend_request`, {
            method: "POST",
            headers: {
                "Authorization": "Bearer " + localStorage.getItem("holdemarena_token"),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ from_uid: uid, accept })
        });
        
        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || "처리 실패");
        }
        
        // 큐에서 제거 후 다음 요청 렌더링
        pendingFriendRequests.shift();
        renderFriendRequest();
        fetchFriends(); // 친구 목록 최신화
        hasPendingFriendRequest = pendingFriendRequests.length > 0;
        updateGlobalFriendIndicator();
    } catch (err) {
        alert("❌ 요청 처리 실패: " + err.message);
    }
}


// 채팅 전송
function sendMessageToFriend(friendUid, content) {
    if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
        chatSocket.send(JSON.stringify({
            type: "friend_chat",  // ✅ 수정
            to: friendUid,         // ✅ 수정
            text: content          // ✅ 수정
        }));
    }
}

async function fetchFriendRequests() {
    try {
        const res = await fetch(`https://${location.hostname}/api/friend_requests`, {
            headers: { Authorization: "Bearer " + localStorage.getItem("holdemarena_token") }
        });
        
        if (!res.ok) throw new Error("친구 요청 목록 실패");
        
        const list = await res.json();
        pendingFriendRequests = list;
        hasPendingFriendRequest = pendingFriendRequests.length > 0;  // ✅ 인디케이터 반영
        renderFriendRequest();
        updateGlobalFriendIndicator();                               // ✅ 반영
    } catch (err) {
        console.error("❌ 친구 요청 목록 에러:", err);
    }
}


async function loadInitialMessages(friendUid) {
    try {
        const res = await fetch(`https://${location.hostname}/api/chat_logs?friend_uid=${friendUid}&limit=20`, {
            headers: { Authorization: "Bearer " + localStorage.getItem("holdemarena_token") }
        });
        const data = await res.json();
        chatMessages = data.messages;
        
        const chatArea = document.querySelector("#chatWindow .flex.flex-col");
        chatArea.innerHTML = "";
        chatMessages.forEach(m => renderIncomingMessage(m));
        
        if (chatMessages.length > 0) {
            oldestTimestamp = chatMessages[0].timestamp;
        }
    } catch (e) {
        console.error("메시지 로딩 실패", e);
    }
}

async function loadOlderMessages(friendUid) {
    if (!oldestTimestamp || isLoading) return;
    isLoading = true;
    
    try {
        const res = await fetch(`https://${location.hostname}/api/chat_logs?friend_uid=${friendUid}&limit=20&before=${oldestTimestamp}`, {
            headers: { Authorization: "Bearer " + localStorage.getItem("holdemarena_token") }
        });
        
        const data = await res.json();
        const chatArea = document.querySelector("#chatScrollWrapper"); // ✅ scroll 대상
        const chatContainer = document.querySelector("#chatScrollContainer"); // ✅ 메시지 append 대상
        const prevScrollHeight = chatArea.scrollHeight;
        
        const newMessages = data.messages;
        newMessages.forEach(m => renderIncomingMessage(m, true)); // prepend
        
        // ✅ 이중 rAF로 scroll 보정 확실히 반영
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                chatArea.scrollTop = chatArea.scrollHeight - prevScrollHeight;
            });
        });
        
        if (newMessages.length > 0) {
            oldestTimestamp = newMessages[0].timestamp;
        }
    } catch (e) {
        console.error("이전 메시지 로딩 실패", e);
    } finally {
        isLoading = false;
    }
}

// 수신한 메시지 렌더링
function renderIncomingMessage(msg, prepend = false) {
    const scrollWrapper = document.getElementById("chatScrollWrapper");
    const scrollContainer = document.getElementById("chatScrollContainer");
    const messageDiv = document.createElement("div");
    
    const myUid = localStorage.getItem("holdemarena_uid");
    const isMine = msg.from === myUid;
    const align = isMine ? "justify-end" : "justify-start";
    const bubbleColor = isMine ? "bg-primary text-white" : "bg-white text-black";
    
    messageDiv.className = `flex ${align}`;
    messageDiv.innerHTML = `
        <div class="${bubbleColor} rounded-lg p-3 max-w-[80%] shadow-sm">
            <p class="text-sm">${msg.text}</p>
            <p class="text-xs mt-1 ${isMine ? "text-white/80" : "text-gray-500"}">
                ${formatRelativeTime(msg.timestamp)}
            </p>
        </div>
    `;
    
    if (prepend) {
        const prevScrollHeight = scrollWrapper.scrollHeight;
        scrollContainer.prepend(messageDiv);
        requestAnimationFrame(() => {
            scrollWrapper.scrollTop = scrollWrapper.scrollHeight - prevScrollHeight;
        });
    } else {
        scrollContainer.appendChild(messageDiv);
        requestAnimationFrame(() => {
            scrollWrapper.scrollTop = scrollWrapper.scrollHeight;
        });
    }
}


function formatRelativeTime(isoString) {
    const now = new Date();
    const then = new Date(isoString + 'Z');
    const diffSeconds = Math.floor((now - then) / 1000);
    
    let value, unit;
    if (diffSeconds < 60) {
        value = -diffSeconds;
        unit = 'second';
    } else if (diffSeconds < 3600) {
        value = -Math.floor(diffSeconds / 60);
        unit = 'minute';
    } else if (diffSeconds < 86400) {
        value = -Math.floor(diffSeconds / 3600);
        unit = 'hour';
    } else if (diffSeconds < 604800) {
        value = -Math.floor(diffSeconds / 86400);
        unit = 'day';
    } else {
        // 7일 이상은 날짜로 표시
        return then.toLocaleDateString(navigator.language, {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    }
    
    const rtf = new Intl.RelativeTimeFormat(navigator.language, { numeric: "auto" });
    return rtf.format(value, unit);
}


async function fetchFriends() {
    try {
        const res = await fetch(`https://${location.hostname}/api/friends`, {
            headers: {
                Authorization: "Bearer " + localStorage.getItem("holdemarena_token")
            }
        });
        
        if (!res.ok) {
            throw new Error("친구 목록 가져오기 실패");
        }
        
        const friendsData = await res.json();
        console.log("📋 친구 목록:", friendsData);
        friends = friendsData;
        friends.forEach(f => {
            onlineStatus[f.uid] = f.online; // ✅ 받아온 온라인 상태 반영
        });
        renderFriendList();
        friendsLoaded = true; // ✅ 친구 목록 로딩 완료
        
        // ✅ 대기 중인 온라인 상태 반영
        pendingStatusUpdates.forEach(({ uid, isOnline }) => {
            updateFriendStatus(uid, isOnline);
        });
        pendingStatusUpdates = []; // 대기큐 비우기
        
    } catch (e) {
        console.error("❌ 친구 목록 에러:", e);
    }
}



function renderFriendList() {
    
    const container = document.querySelector("#sideNav .divide-y");
    container.innerHTML = "";
    
    if (!friends || friends.length === 0) {
        container.innerHTML = `<div class="text-center text-gray-400 p-4">No friends yet</div>`;
    }
    
    const sortedFriends = [...friends].sort((a, b) => {
        const aOnline = onlineStatus[a.uid] ? 1 : 0;
        const bOnline = onlineStatus[b.uid] ? 1 : 0;
        return bOnline - aOnline;
    });
    
    for (const friend of sortedFriends) {
        const isOnline = !!onlineStatus[friend.uid];
        
        const friendDiv = document.createElement("div");
        friendDiv.className = "p-3 flex items-center hover:bg-gray-50 cursor-pointer";
        friendDiv.dataset.uid = friend.uid;
        
        friendDiv.innerHTML = `
            <div class="w-4 h-4 rounded-full ${isOnline ? "bg-green-500" : "bg-gray-400"} mr-3" id="status-${friend.uid}"></div>
            <div class="flex-1">
                <p class="font-medium text-gray-800">${friend.username}</p>
                <p class="text-xs ${isOnline ? "text-green-600" : "text-gray-400"}" id="last-seen-${friend.uid}">
                    ${isOnline ? "Online" : "Offline"}
                </p>
            </div>
        `;
        if (friend.has_unread || unreadFlags[friend.uid]) {
            friendDiv.innerHTML += `
                <div class="flex items-center gap-2">
                    <div class="w-3 h-3 bg-[radial-gradient(closest-side,#d4af37_45%,#e9c767_85%,white_100%)] rounded-full animate-pulse"></div>
                </div>
            `;
        }
        
        container.appendChild(friendDiv);
        
        friendDiv.addEventListener("click", () => {
            openChatWindow(friend.uid, friend.username);
        });
    }
    
    // ✅ 온라인 친구 수 갱신
    const onlineCount = Object.values(onlineStatus).filter(v => v).length;
    const onlineCountText = document.querySelector("#sideNav .text-sm");
    if (onlineCountText) {
        onlineCountText.innerHTML = `<span class="text-green-500 font-medium">${onlineCount}</span> Online`;
    }
    
    updateGlobalFriendIndicator();
}



function updateFriendStatus(uid, isOnline) {
    
    onlineStatus[uid] = isOnline;
    
    const statusDot = document.getElementById(`status-${uid}`);
    const lastSeenText = document.getElementById(`last-seen-${uid}`);
    
    if (statusDot && lastSeenText) {
        statusDot.className = `w-4 h-4 rounded-full mr-3 ${isOnline ? "bg-green-500" : "bg-gray-400"}`;
        lastSeenText.textContent = isOnline ? "Online" : "Offline";
    } else {
        console.warn("❗ 상태 dot이나 텍스트를 찾을 수 없음", uid);
    }
}


async function openChatWindow(friendUid, friendName) {
    currentChatFriendUid = friendUid;
    chatMessages = [];
    oldestTimestamp = null;
    isLoading = false;
    
    document.querySelector("#chatWindow .font-medium").textContent = friendName;
    document.getElementById("chatWindow").classList.remove("translate-y-full");
    isChatOpen = true;
    
    const chatArea = document.getElementById("chatScrollContainer");
    chatArea.innerHTML = "";
    
    await loadInitialMessages(friendUid);
    
    try {
        await fetch(`https://${location.hostname}/api/mark_read`, {
            method: "POST",
            headers: {
                "Authorization": "Bearer " + localStorage.getItem("holdemarena_token"),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ friend_uid: friendUid })
        });
        
        // ✅ 🔥 클라이언트 플래그도 삭제
        delete unreadFlags[friendUid];
        
        // ✅ 서버 상태 최신화
        await fetchFriends();
        renderFriendList();
        
    } catch (e) {
        console.error("읽음 처리 실패", e);
    }
}

function updateGlobalFriendIndicator() {
    const indicator = document.getElementById("friend-global-indicator");
    
    const hasAnyUnread = Object.values(unreadFlags).some(v => v) ||
    friends.some(friend => friend.has_unread) ||
    hasPendingFriendRequest ||
    hasPendingInviteRequest;
    
    if (hasAnyUnread) {
        indicator.classList.remove("hidden");
    } else {
        indicator.classList.add("hidden");
    }
}


async function fetchUsername() {
    try {
        const res = await fetch("/api/me", {
            headers: { Authorization: "Bearer " + localStorage.getItem("holdemarena_token") }
        });
        
        if (res.status === 401) {
            location.href = "/";
            return;
        }
        if (!res.ok) {
            throw new Error("Failed to fetch username");
        }
        
        const data = await res.json();
        
        const nameEl = document.querySelector("#p1_name");
        if (nameEl) {
            nameEl.textContent = data.username;
        }        
        
        // ✅ username, uid를 로컬에 저장
        if (data.uid) localStorage.setItem("holdemarena_uid", data.uid);
        if (data.username) localStorage.setItem("holdemarena_username", data.username);
        
        console.log("✅ 내 UID/이름 저장됨:", data.uid, data.username);
    } catch (e) {
        console.error("username 가져오기 실패", e);
    }
}

document.addEventListener("DOMContentLoaded", fetchUsername);


const friendsButton = document.getElementById('friends');
const sideNav = document.getElementById('sideNav');
const closeSideNav = document.getElementById('closeSideNav');
const addFriendButton = document.getElementById('addFriendButton');
const chatWindow = document.getElementById('chatWindow');
const chatHeader = document.getElementById('chatHeader');
const minimizeChat = document.getElementById('minimizeChat');
let isChatMinimized = true;

addFriendButton.addEventListener('click', (e) => {
    e.stopPropagation();
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60]';
    modal.innerHTML = `
    <div class="bg-white rounded-lg p-6 w-5/6 max-w-md">
        <div class="flex justify-between items-center mb-4">
            <h3 class="text-lg font-semibold">Add Friend</h3>
            <button class="text-gray-400 hover:text-gray-600" id="closeAddFriend">
                <i class="ri-close-line ri-lg"></i>
            </button>
        </div>
        <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700 mb-1">Nickname</label>
            <input type="text" id="friendNameInput" placeholder="Enter friend's nickname" class="w-full px-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-primary">
        </div>
        <button id="confirmAddFriend" class="w-full py-3 bg-primary text-white rounded-button hover:bg-primary/90 transition-colors">
            Add Friend
        </button>
    </div>
    `;
    document.body.appendChild(modal);
    
    // 닫기 버튼
    document.getElementById('closeAddFriend').onclick = () => {
        document.body.removeChild(modal);
    };
    
    // 바깥 클릭시 닫기
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            document.body.removeChild(modal);
        }
    });
    
    // "Add Friend" 버튼 클릭 시
    document.getElementById('confirmAddFriend').onclick = async () => {
        const nickname = document.getElementById('friendNameInput').value.trim();
        if (!nickname) return alert("닉네임을 입력하세요.");
        
        try {
            const res = await fetch(`https://${location.hostname}/api/send_friend_request`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + localStorage.getItem("holdemarena_token")
                },
                body: JSON.stringify({ username: nickname })
            });
            
            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.detail || "친구 요청 실패");
            }
            
            document.body.removeChild(modal);
        } catch (err) {
            alert("❌ 친구 요청 실패: " + err.message);
        }
    };    
});
friendsButton.addEventListener('click', () => {
    const opened = sideNav.classList.toggle('translate-x-full');
    const blur = document.getElementById("blurOverlay");
    if (!opened) {
        blur.classList.remove("hidden");
    } else {
        blur.classList.add("hidden");
    }
});
closeSideNav.addEventListener('click', () => {
    sideNav.classList.add('translate-x-full');
    document.getElementById("blurOverlay").classList.add("hidden");
});
document.getElementById("blurOverlay").addEventListener("click", () => {
    sideNav.classList.add("translate-x-full");
    chatWindow.classList.add("translate-y-full");
    document.getElementById("blurOverlay").classList.add("hidden");
    isChatOpen = false;
});
document.querySelectorAll('#sideNav .hover\\:bg-gray-50').forEach(friend => {
    friend.addEventListener('click', () => {
        chatWindow.classList.remove('translate-y-full');
        isChatMinimized = false;
    });
});

chatHeader.addEventListener('click', (e) => {
    if (e.target.closest('#minimizeChat')) return;
    if (isChatMinimized) {
        chatWindow.classList.remove('translate-y-full');
    } else {
        chatWindow.classList.add('translate-y-full');
    }
    isChatMinimized = !isChatMinimized;
});
minimizeChat.addEventListener('click', () => {
    chatWindow.classList.add('translate-y-full');
    isChatMinimized = true;
    isChatOpen = false;
});





















// Game, Party


document.addEventListener('DOMContentLoaded', function() {
    connectQueueSocket();
    init_player_slot_click_handler();
    init_find_match_btn_handler();
});

function init_player_slot_click_handler(){
    // Player slot click handler
    const playerSlots = document.querySelectorAll('.player-slot');
    playerSlots.forEach(slot => {
        slot.addEventListener('click', function () {
            const inviteModal = document.createElement('div');
            inviteModal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
            inviteModal.innerHTML = `
    <div class="bg-white rounded-lg p-6 w-5/6 max-w-md">
        <div class="flex justify-between items-center mb-4">
            <h3 class="text-lg font-semibold">Invite Player</h3>
            <button class="text-gray-400 hover:text-gray-600" id="closeInvite">
                <i class="ri-close-line ri-lg"></i>
            </button>
        </div>
        <div class="mb-4">
            <div class="relative">
                <input type="text" id="inviteNameInput" placeholder="Search friends..." class="w-full px-4 py-2 pr-10 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-primary">
                <div class="absolute right-3 top-1/2 transform -translate-y-1/2">
                    <i class="ri-search-line text-gray-400"></i>
                </div>
            </div>
        </div>
        <div class="max-h-60 overflow-y-auto mb-4">
            <div class="space-y-2">
                <div class="flex items-center justify-between p-2 hover:bg-gray-50 rounded-lg cursor-pointer">
                </div>
            </div>
        </div>
        <button id="sendInviteBtn" class="w-full py-3 bg-primary text-white rounded-button hover:bg-primary/90 transition-colors">
            Send Invites
        </button>
    </div>
    `;
            document.body.appendChild(inviteModal);
            
            requestAnimationFrame(() => {
                const closeButton = inviteModal.querySelector('#closeInvite');
                if (closeButton) {
                    closeButton.addEventListener('click', () => {
                        document.body.removeChild(inviteModal);
                    });
                }
                
                inviteModal.addEventListener('click', (e) => {
                    if (e.target === inviteModal) {
                        document.body.removeChild(inviteModal);
                    }
                });
                
                const sendButton = inviteModal.querySelector('#sendInviteBtn');
                if (sendButton) {
                    sendButton.addEventListener("click", async () => {
                        const nameInput = inviteModal.querySelector("#inviteNameInput");
                        const nickname = nameInput?.value.trim();
                        if (!nickname) {
                            alert("닉네임을 입력해주세요.");
                            return;
                        }
                        
                        try {
                            const res = await fetch("/api/party/invite", {
                                method: "POST",
                                headers: {
                                    "Authorization": "Bearer " + localStorage.getItem("holdemarena_token"),
                                    "Content-Type": "application/json"
                                },
                                body: JSON.stringify({ username: nickname })
                            });
                            
                            if (!res.ok) {
                                const data = await res.json();
                                throw new Error(data.detail || "초대 실패");
                            }
                            
                            document.body.removeChild(inviteModal);
                        } catch (err) {
                            alert("❌ 초대 실패: " + err.message);
                        }
                    });
                }
            });
        });
    });
}

function init_find_match_btn_handler(){
    const findMatchBtn = document.getElementById('findMatchBtn');
    
    findMatchBtn.onclick = function () {
        if (isQueueing) return; // ✅ 중복 클릭 차단
        
        fetch("/api/join_quick_play_queue", {
            method: "POST",
            headers: { Authorization: "Bearer " + localStorage.getItem("holdemarena_token") }
        }).then(res => {
            if (res.status === 401) {
                location.href = "/";
            }
        }).catch(err => {
            console.error("큐 참가 실패:", err);
        });
    };
}

function connectQueueSocket(onReady) {
    queueSocket = new WebSocket(`wss://${location.hostname}/quick_play_party_queue_ws?token=${token}`);
    
    queueSocket.onopen = () => {
        console.log("✅ Queue WebSocket 연결됨");
        if (onReady) onReady();
        isConnectedtoQueueSocket = true;
        clearTimeout(reconnectTimer);
        reconnectCount = 0;
        hideReconnectBanner();
    };
    
    queueSocket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        console.log("📩", msg);
        
        if (msg.type === "party_status") {
            renderPartyUI(msg.leader_uid, msg.members, localStorage.getItem("holdemarena_uid"));
        }
        
        if (msg.type === "party_queue_status") {
            isQueueing = msg.is_queueing;
            if (isQueueing) startLoadingBar(); // ✅ UI 갱신 함수 호출
            else {
                const loadingModal = document.getElementById("loadingModal");
                if (loadingModal) loadingModal.remove();
            }
        }
        
        if (msg.type === "match_ready") {
            showTableFoundModal();  // 로딩바는 없애지 않고 그냥 테이블 찾았다는 모달만 띄움
        }
        
        if (msg.type === "match_success") {
            localStorage.setItem("holdemarena_game_id", msg.game_id);
            localStorage.setItem("holdemarena_player_id", msg.player_id);
            localStorage.setItem("holdemarena_uid", msg.uid);
            localStorage.setItem("holdemarena_hostname", location.hostname);
            location.href = "game.html";
        }
    };
    
    queueSocket.onclose = (event) => {
        isConnectedtoQueueSocket = false;
        console.warn("❌ Game WebSocket 끊김 → 재연결 시도 중...");
        if (event.code === 1006) {
            window.history.back();
        }
        reconnectTimer = setTimeout(connectqueueSocket, 3000);
        showReconnectBanner();
    };
}


function renderNextPartyInvite() {
    const container = document.querySelector("#sideNav .bg-primary\\/5");
    if (!container || pendingPartyInvites.length === 0) return;
    
    const invite = pendingPartyInvites[0];
    container.innerHTML = `
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center">
                    <i class="ri-user-add-line text-primary"></i>
                </div>
                <div>
                    <p class="text-sm font-medium text-black">${invite.from_username}</p>
                    <p class="text-xs text-gray-500">invited you to Quick Play</p>
                </div>
            </div>
            <div class="flex items-center gap-2">
                <button class="w-7 h-7 bg-green-500 text-white rounded-full flex items-center justify-center hover:bg-green-600 transition-colors"
                        onclick="acceptPartyInvite('${invite.leader_uid}')">
                    <i class="ri-check-line"></i>
                </button>
                <button class="w-7 h-7 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors"
                        onclick="dismissPartyInvite()">
                    <i class="ri-close-line"></i>
                </button>
            </div>
        </div>
    `;
}

async function renderPartyUI(leaderUid, memberList, myUid) {
    const container = document.querySelector(".grid.grid-cols-2");
    if (!container) return;
    container.innerHTML = "";
    
    const uidToName = {};
    const memberUids = [];
    
    for (const m of memberList) {
        uidToName[m.uid] = m.username;
        memberUids.push(m.uid);
    }
    
    // ✅ 인원 수 갱신
    const playerCountElement = document.querySelector("#player-count"); // ID는 아래 참고
    if (playerCountElement) {
        playerCountElement.textContent = `Players (${memberUids.length}/8)`;
    }
    
    for (let i = 0; i < 8; i++) {
        const uid = memberUids[i];
        const isLeader = uid === leaderUid;
        const isMe = uid === myUid;
        
        const slot = document.createElement("div");
        
        if (uid) {
            const canControl = (myUid === leaderUid) && (uid !== myUid);
            let controlHTML = "";
            if (canControl) {
                controlHTML = `
                    <div class="flex gap-2 mt-2">
                        <button class="text-xs px-2 py-1 bg-red-500 text-white rounded" onclick="kickPlayer('${uid}')">Kick</button>
                        <button class="text-xs px-2 py-1 bg-gray-500 text-white rounded" onclick="promotePlayer('${uid}')">Promote</button>
                    </div>
                `;
            }
            
            slot.className = "player-slot-active rounded-lg p-3 h-[64px] flex flex-col items-center justify-center";
            slot.innerHTML = `
                <p class="text-sm font-medium">${uidToName[uid] || uid}</p>
                <p class="text-xs text-gray-500">${isLeader ? "Host" : (isMe ? "You" : "Member")}</p>
                ${controlHTML}
            `;
        } else {
            // 빈 슬롯
            slot.className = "player-slot rounded-lg p-3 h-[64px] flex flex-col items-center justify-center cursor-pointer";
            slot.innerHTML = `
                <div class="w-10 h-10 rounded-full border-2 border-dashed border-gray-300 flex items-center justify-center">
                    <i class="ri-add-line ri-lg text-gray-400"></i>
                </div>
            `;
            
            // ✅ 초대 모달 오픈 이벤트
            slot.addEventListener("click", () => {
                const inviteModal = document.createElement("div");
                inviteModal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
                inviteModal.innerHTML = `
                    <div class="bg-white rounded-lg p-6 w-5/6 max-w-md">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-lg font-semibold">Invite Player</h3>
                            <button class="text-gray-400 hover:text-gray-600" id="closeInvite">
                                <i class="ri-close-line ri-lg"></i>
                            </button>
                        </div>
                        <div class="mb-4">
                            <input type="text" placeholder="Search friends..." class="w-full px-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-primary">
                        </div>
                        <div class="max-h-60 overflow-y-auto mb-4">
                            <div class="space-y-2">
                                <p class="text-sm text-gray-500 text-center">Your friend list will go here.</p>
                            </div>
                        </div>
                        <button class="w-full py-3 bg-primary text-white rounded-button hover:bg-primary/90 transition-colors">
                            Send Invites
                        </button>
                    </div>
                `;
                document.body.appendChild(inviteModal);
                
                const myPartyMemberUids = new Set(memberUids);
                const onlineFriends = friends.filter(f =>
                    onlineStatus[f.uid] && !myPartyMemberUids.has(f.uid)
                );
                const listContainer = inviteModal.querySelector(".space-y-2");
                listContainer.innerHTML = "";
                
                for (const f of onlineFriends) {
                    const item = document.createElement("div");
                    item.className = "flex items-center justify-between p-2 hover:bg-gray-50 rounded-lg cursor-pointer";
                    item.innerHTML = `
                        <div class="flex items-center">
                            <div class="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center mr-2">
                                <i class="ri-user-3-line text-primary"></i>
                            </div>
                            <div>
                                <p class="text-sm font-medium">${f.username}</p>
                                <p class="text-xs text-green-600">Online</p>
                            </div>
                        </div>
                        <button class="w-7 h-7 flex items-center justify-center bg-primary/10 text-primary rounded-full"
                                onclick="sendbtnonclick(this)">
                            <i class="ri-add-line"></i>
                        </button>
                    `;
                    item.querySelector("button").username = f.username;
                    listContainer.appendChild(item);
                }
                
                // 닫기 버튼 처리
                const closeButton = inviteModal.querySelector('#closeInvite');
                if (closeButton) {
                    closeButton.addEventListener('click', () => {
                        document.body.removeChild(inviteModal);
                    });
                }
                
                // 바깥 영역 클릭 시 닫기
                inviteModal.addEventListener('click', (e) => {
                    if (e.target === inviteModal) {
                        document.body.removeChild(inviteModal);
                    }
                });
                
                // Send Invites 버튼 핸들러 추가
                const sendBtn = inviteModal.querySelector(".w-full.bg-primary");
                if (sendBtn) {
                    sendBtn.addEventListener("click", async () => {
                        const input = inviteModal.querySelector("input[type=text]");
                        const nickname = input?.value.trim();
                        if (!nickname) {
                            alert("닉네임을 입력해주세요.");
                            return;
                        }
                        
                        try {
                            const res = await fetch("/api/party/invite", {
                                method: "POST",
                                headers: {
                                    Authorization: "Bearer " + localStorage.getItem("holdemarena_token"),
                                    "Content-Type": "application/json"
                                },
                                body: JSON.stringify({ username: nickname })
                            });
                            
                            if (!res.ok) {
                                const data = await res.json();
                                throw new Error(data.detail || "초대 실패");
                            }
                            
                            document.body.removeChild(inviteModal);
                        } catch (e) {
                            alert("초대 실패: " + e.message);
                        }
                    });
                }
            });
        }
        
        container.appendChild(slot);
    }
    
    // ✅ "Find Match" 버튼 표시 여부
    const btn = document.getElementById("findMatchBtn");
    if (btn) {
        if (myUid === leaderUid && isConnectedtoQueueSocket) {
            btn.textContent = "Find Match";
            btn.disabled = false;
            btn.classList.remove("opacity-50", "cursor-not-allowed");
            btn.classList.add("hover:bg-primary/90");
        } else {
            btn.textContent = "Host will find match";
            btn.disabled = true;
            btn.classList.add("opacity-50", "cursor-not-allowed");
            btn.classList.remove("hover:bg-primary/90");
        }
    }
}

function sendbtnonclick(el){
    inviteByUsername(el.username);
    const icone = el.querySelector('.ri-add-line');
    icone.classList.remove('ri-add-line');
    icone.classList.add('ri-check-line');
}



function showReconnectBanner() {
    const existing = document.getElementById("ws-reconnect-banner");
    if (existing) return;
    
    const banner = document.createElement("div");
    banner.id = "ws-reconnect-banner";
    banner.className = "fixed top-0 left-0 right-0 bg-red-500 text-white text-sm text-center py-2 z-50";
    banner.textContent = "🔌 연결 끊김. 다시 연결 중...";
    document.body.appendChild(banner);
}

function hideReconnectBanner() {
    const banner = document.getElementById("ws-reconnect-banner");
    if (banner) banner.remove();
}

async function loadPartyStatus() {
    const res = await fetch("/api/party/status", {
        headers: { Authorization: "Bearer " + localStorage.getItem("holdemarena_token") }
    });
    const data = await res.json();
    console.log("🎉 파티 상태:", data);
    // TODO: HTML 내 player slot 갱신
}

function showPartyInviteModal(fromUsername, leaderUid) {
    const container = document.querySelector("#sideNav .bg-primary\\/5");
    if (!container) return;
    
    container.innerHTML = `
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center">
                    <i class="ri-user-add-line text-primary"></i>
                </div>
                <div>
                    <p class="text-sm font-medium text-black">${fromUsername}</p>
                    <p class="text-xs text-gray-500">invited you to Quick Play</p>
                </div>
            </div>
            <div class="flex items-center gap-2">
                <button class="w-7 h-7 bg-green-500 text-white rounded-full flex items-center justify-center hover:bg-green-600 transition-colors"
                        onclick="acceptPartyInvite('${leaderUid}')">
                    <i class="ri-check-line"></i>
                </button>
                <button class="w-7 h-7 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors"
                        onclick="dismissPartyInvite()">
                    <i class="ri-close-line"></i>
                </button>
            </div>
        </div>
    `;
}

async function inviteByUsername(username) {
    try {
        const res = await fetch("/api/party/invite", {
            method: "POST",
            headers: {
                "Authorization": "Bearer " + localStorage.getItem("holdemarena_token"),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ username })
        });
        
        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || "초대 실패");
        }
    } catch (err) {
        alert("❌ 초대 실패: " + err.message);
    }
}

async function acceptPartyInvite(leaderUid) {
    try {
        const res = await fetch("/api/party/accept", {
            method: "POST",
            headers: {
                Authorization: "Bearer " + localStorage.getItem("holdemarena_token"),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ leader_uid: leaderUid })
        });
        
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || "서버 오류");
        }
        
        dismissPartyInvite(); // ✅ 성공 시만 제거
    } catch (e) {
        alert("초대 수락 실패: " + e.message);
    }
}

function dismissPartyInvite() {
    const container = document.querySelector("#sideNav .bg-primary\\/5");
    if (container) container.innerHTML = "";
    
    const removedInvite = pendingPartyInvites.shift(); // ❗ 큐에서 제거
    if (removedInvite) {
        pendingPartyInviteLeaders.delete(removedInvite.leader_uid); // ✅ 중복 방지 세트에서 제거
    }
    
    hasPendingInviteRequest = pendingPartyInvites.length > 0;
    renderNextPartyInvite(); // 다음 초대 표시
    updateGlobalFriendIndicator();
}

async function exit() {
    try {
        const res = await fetch(`/api/party/leave`, {
            method: "POST",  // 👈 반드시 추가
            headers: { Authorization: "Bearer " + localStorage.getItem("holdemarena_token") }
        });
    } catch (err) {
        return;
    } finally {
        window.history.back();
    }
}

async function kickPlayer(uid) {
    try {
        const res = await fetch("/api/party/kick", {
            method: "POST",
            headers: {
                Authorization: "Bearer " + localStorage.getItem("holdemarena_token"),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ target_uid : uid })
        });
        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || "추방 실패");
        }
    } catch (err) {
        alert("❌ 추방 실패: " + err.message);
    }
}

async function promotePlayer(uid) {
    try {
        const res = await fetch("/api/party/promote", {
            method: "POST",
            headers: {
                Authorization: "Bearer " + localStorage.getItem("holdemarena_token"),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ target_uid : uid })
        });
        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || "위임 실패");
        }
    } catch (err) {
        alert("❌ 위임 실패: " + err.message);
    }
}



function startLoadingBar() {
    loadingModal = document.createElement('div');
    loadingModal.id = "loadingModal"
    loadingModal.className = 'fixed top-[56px] left-0 right-0 bg-white shadow-md z-40';
    loadingModal.innerHTML = `
<div class="p-3 flex items-center justify-between">
<div class="flex items-center gap-3">
<div class="w-6 h-6 relative">
  <div class="absolute inset-0 border-2 border-primary/20 rounded-full"></div>
  <div class="absolute inset-0 border-2 border-primary rounded-full animate-spin" style="border-top-color: transparent"></div>
</div>
<div class="flex-1">
  <p class="text-sm font-medium">Finding Table...</p>
  <div class="flex items-center gap-2 text-xs text-gray-500">
    <span class="waiting-time">00:00</span>
    <span>•</span>
    <span>Expected: ~2 min</span>
  </div>
</div>
</div>
<button id="cancelSearch" class="text-gray-400 hover:text-gray-600 p-1">
<i class="ri-close-line ri-lg"></i>
</button>
</div>
    `;
    document.body.appendChild(loadingModal);
    
    const waitingTimeElement = loadingModal.querySelector('.waiting-time');
    waitingSeconds = 0;
    waitingInterval = setInterval(() => {
        waitingSeconds++;
        const minutes = Math.floor(waitingSeconds / 60);
        const seconds = waitingSeconds % 60;
        waitingTimeElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    }, 1000);
    
    document.getElementById('cancelSearch').onclick = function() {
        fetch("/api/leave_queue", {
            method: "POST",
            headers: { Authorization: "Bearer " + localStorage.getItem("holdemarena_token") }
        }).then(res => {
            if (res.status === 401) {
                location.href = "/";
            }
        }).finally(() => {
            clearInterval(waitingInterval);
            loadingModal.remove();
        });
    };
}

function showTableFoundModal() {
    const successModal = document.createElement('div');
    successModal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
    successModal.innerHTML = `
<div class="bg-white rounded-lg p-6 w-5/6 max-w-md text-center">
<div class="w-16 h-16 mx-auto bg-green-100 rounded-full flex items-center justify-center mb-4">
<i class="ri-check-line ri-2x text-green-600"></i>
</div>
<h3 class="text-xl font-bold mb-2">Table Found!</h3>
<p class="text-sm text-gray-600 mb-6">Press OK within 8 seconds to join the table</p>
<div class="flex justify-center flex-col items-center gap-3">
<div class="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
<div class="countdown-bar h-full bg-primary transition-all duration-[8000ms] ease-linear" style="width: 100%"></div>
</div>
<button id="okButton" class="px-6 py-3 bg-primary text-white rounded-button hover:bg-primary/90 transition-colors w-32">OK (8)</button>
</div>
</div>
`;
    document.body.appendChild(successModal);
    
    const okButton = document.getElementById('okButton');
    const countdownBar = successModal.querySelector('.countdown-bar');
    let timeLeft = 8;
    
    requestAnimationFrame(() => {
        // 3. 두 번째 rAF → 0%로 줄이기
        requestAnimationFrame(() => {
            countdownBar.style.width = '0%';
        });
    });
    
    let countdownInterval = setInterval(() => {
        timeLeft--;
        okButton.textContent = `OK (${timeLeft})`;
        if (timeLeft <= 0) {
            clearInterval(countdownInterval);
            successModal.remove();
            if (loadingModal) loadingModal.remove(); // ✅ OK 안 눌렀으니까 로딩바 제거!
            showTimeoutModal();
        }
    }, 1000);
    
    okButton.onclick = function () {
        if (queueSocket && queueSocket.readyState === WebSocket.OPEN) {
            queueSocket.send(JSON.stringify({ type: "accept_match" }));
        }
        successModal.remove();
    };
}

function showTimeoutModal() {
    const timeoutModal = document.createElement('div');
    timeoutModal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
    timeoutModal.innerHTML = `
<div class="bg-white rounded-lg p-6 w-5/6 max-w-md text-center">
<div class="w-16 h-16 mx-auto bg-red-100 rounded-full flex items-center justify-center mb-4">
<i class="ri-close-line ri-2x text-red-600"></i>
</div>
<h3 class="text-xl font-bold mb-2">Time Out!</h3>
<p class="text-sm text-gray-600 mb-6">You didn't confirm in time. Please try again.</p>
<button id="tryAgainButton" class="px-6 py-3 bg-primary text-white rounded-button hover:bg-primary/90 transition-colors">Try Again</button>
</div>
`;
    document.body.appendChild(timeoutModal);
    
    document.getElementById('tryAgainButton').onclick = function() {
        timeoutModal.remove();
    };
}

function check_unfinished_game(){
    const isingame = false;
    const game_ws = new WebSocket(`wss://${location.hostname}/quick_play_ws?token=${token}`);
    game_ws.onopen = () => {
        console.log("✅ Quick play Party/Queue WebSocket 연결됨");
    };
    game_ws.onmessage = (e) => {
        const msg = e.data;
        data = JSON.parse(msg);
        if(data.type === "error"){
            game_ws.close();
        }
        else{
            game_ws.close();
            const modal = document.createElement('div');
            modal.className = 'fixed inset-0 z-[80] flex items-center justify-center';
            modal.innerHTML = `
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm"></div>
        <div class="relative bg-white rounded-lg p-6 w-5/6 max-w-md">
            <div class="text-center mb-6">
            <div class="w-16 h-16 mx-auto bg-primary/10 rounded-full flex items-center justify-center mb-4">
                <i class="ri-logout-box-line ri-2x text-primary"></i>
            </div>
            <h3 class="text-xl font-bold mb-2">Reconnect</h3>
            <p class="text-sm text-gray-600">You're already in a game. Would you like to reconnect?</p>
            </div>
            <div class="flex space-x-3">
            <button class="flex-1 py-3 border border-gray-200 rounded-button text-gray-700 hover:bg-gray-50 transition-colors" id="cancelReconnect">Cancel</button>
            <button class="flex-1 py-3 bg-primary text-white rounded-button hover:bg-primary/90 transition-colors" id="confirmReconnect">Reconnect</button>
            </div>
        </div>
        `;
            
            document.body.appendChild(modal);
            
            const cancelButton = modal.querySelector('#cancelReconnect');
            const confirmButton = modal.querySelector('#confirmReconnect');
            
            modal.addEventListener('click', (e) => {
                if (e.target === modal.querySelector('.absolute')) {
                document.body.removeChild(modal);
                }
            });
            
            cancelButton.addEventListener('click', () => {
                document.body.removeChild(modal);
            });
            
            confirmButton.addEventListener('click', () => {
                document.body.removeChild(modal);
                window.location.href = '/static/game.html';
            });
        }
    };
}