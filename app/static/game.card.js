const handleQ = [];
let handling = false;



function setCardDry(cardID, text){
  // cardID: ex) cc1 => community card 1
  //             p1c1 => player 1 card 1
  let id = "";
  if (cardID[0] === "c"){
    id += `ccard${cardID[2]}`;
  }
  else{
    id += `p${cardID[1]}_card${cardID[3]}`;
  }
  let cardEl = document.getElementById(`${id}_card`);
  if (!cardEl){
    console.log("wrong cardID: ", cardID);
  }
  let textEl = document.getElementById(`${id}_text`);
  const isHeartOrDiamond = text[1] === "♥" || text[1] === "♦";
  
  cardEl.style.transition = "none";
  if (cardID[0] === "c"){ // 커뮤니티 카드일 경우 항상 보임
    if (isHeartOrDiamond){
      textEl.classList.remove("text-black");
      textEl.classList.add("text-red-600");
    }
    else{
      textEl.classList.remove("text-red-600");
      textEl.classList.add("text-black");
    }
    textEl.innerText = text[0] === "T" ? "10" + text[1] : text;

    cardEl.classList.remove("flipped");
  }
  else{ // 홀카드일 경우 p1은 항상 보이고 나머지는 상태에 따라
    const isP1 = cardID[1] === "1";
    if (isHeartOrDiamond){
      textEl.classList.remove("text-black");
      textEl.classList.add("text-red-600");
    }
    else{
      textEl.classList.remove("text-red-600");
      textEl.classList.add("text-black");
    }
    if (isP1){
      textEl.innerText = text[0] === "T" ? "10" + text[1] : text;;
    }
    else{
      const isFlipped = text === "??";
      if (!isFlipped){
        cardEl.classList.remove("flipped");
        textEl.innerText = text[0] === "T" ? "10" + text[1] : text;
      }
    }
  }

  cardEl.classList.remove("invisible");
  // 다음 프레임에 transition 복구
  requestAnimationFrame(() => {
    cardEl.style.transition = "";
  });
}


function initCCards(){
  const cc = document.getElementById("ccards");
  cc.innerHTML = '';
  for(let i=1;i<6;i++){
    cc.innerHTML += `
      <div id="ccard${i}_card" class="card w-8 h-12 rounded-md flipped invisible">
        <div class="card-inner">
          <div id="ccard${i}_text" class="card-front bg-white text-red-600 font-bold text-sm rounded-md">Q♥</div>
          <div class="card-back bg-white text-secondary text-xl rounded-md">♠</div>
        </div>
      </div>
      `
  }
}

function initPCards(){
  for(let i=1;i<9;i++){
    const hand = document.getElementById(`p${i}_hand`);
    hand.innerHTML = '';
    for(let j=1;j<3;j++){
      if(i == 1){
        hand.innerHTML += `
          <div id="p1_card${j}_card" class="card w-14 h-20 rounded-md flipped invisible">
            <div class="card-inner">
              <div id="p1_card${j}_text" class="card-front bg-white text-red-600 font-bold text-xl rounded-md">A♥</div>
              <div class="card-back bg-white text-secondary text-4xl rounded-md">♠</div>
            </div>
          </div>
          `;
      }
      else{
        hand.innerHTML += `
          <div id="p${i}_card${j}_card" class="card w-8 h-12 rounded flipped invisible">
            <div class="card-inner">
              <div id="p${i}_card${j}_text" class="card-front bg-white text-red-600 font-bold text-xs rounded">10♥</div>
              <div class="card-back bg-white text-secondary text-xl rounded">♠</div>
            </div>
          </div>
          `;
      }
    }
  }
}

function requestCardMotion(type, cardID, text){
  // type: "deal" or "open"
  // cardID: ex) cc1 => community card 1
  //             p1c1 => player 1 card 1
  handleQ.push([type, cardID, text]);
  if (!handling) {
    handling = true;
    handleCardMotion();
  }
}

function handleCardMotion(){
  if (handleQ.length == 0){
    handling = false;
    return;
  }
  let [type, cardID, text] = handleQ.shift();
  if (type === "deal"){
    dealCard(cardID, text);
  }
  else if (type === "open"){
    openCard(cardID, text);
  }
  setTimeout(handleCardMotion, 250);
}

function openCard(cardID, text){
  // only a hole card of a player is allowed to apply this function
  id = `p${cardID[1]}_card${cardID[3]}`;
  let cardEl = document.getElementById(`${id}_card`);
  if (!cardEl){
    console.log("wrong cardID: ", cardID);
  }
  let textEl = document.getElementById(`${id}_text`);

  const isHeartOrDiamond = text[1] === "♥" || text[1] === "♦";
  if (isHeartOrDiamond){
    textEl.classList.remove("text-black");
    textEl.classList.add("text-red-600");
  }
  else{
    textEl.classList.remove("text-red-600");
    textEl.classList.add("text-black");
  }
  textEl.innerText = text[0] === "T" ? "10" + text[1] : text;
  flip(cardEl);
}

function dealCard(cardID, text){
  // cardID: ex) cc1 => community card 1
  //             p1c1 => player 1 card 1
  let id = "";
  if (cardID[0] === "c"){
    id += `ccard${cardID[2]}`;
  }
  else{
    id += `p${cardID[1]}_card${cardID[3]}`;
  }
  let cardEl = document.getElementById(`${id}_card`);
  if (!cardEl){
    console.log("wrong cardID: ", cardID);
  }
  let textEl = document.getElementById(`${id}_text`);
  const isHeartOrDiamond = text[1] === "♥" || text[1] === "♦";

  if (cardID[0] === "c"){ // 커뮤니티 카드일 경우 딜링하면서 플립
    if (isHeartOrDiamond){
      textEl.classList.remove("text-black");
      textEl.classList.add("text-red-600");
    }
    else{
      textEl.classList.remove("text-red-600");
      textEl.classList.add("text-black");
    }
    textEl.innerText = text[0] === "T" ? "10" + text[1] : text;

    cardEl.classList.remove("invisible");
    dealAndFlip(cardEl);
  }
  else{ // 홀카드일 경우 딜링만 함. p1이면서 ??가 아니면 보이게 주고 나머지는 뒷면
    const isP1 = cardID[1] === "1";
    if (isP1 && text !== "??"){
      if (isHeartOrDiamond){
        textEl.classList.remove("text-black");
        textEl.classList.add("text-red-600");
      }
      else{
        textEl.classList.remove("text-red-600");
        textEl.classList.add("text-black");
      }
      textEl.innerText = text[0] === "T" ? "10" + text[1] : text;

      cardEl.style.transition = "none";
      // flipped 제거
      cardEl.classList.remove("flipped");
      deal(cardEl);
      // 다음 프레임에 transition 복구
      requestAnimationFrame(() => {
        cardEl.style.transition = "";
      });
    }
    else{
      deal(cardEl);
    }
  }
}

function deal(cardEl){
  cardEl.classList.remove("invisible");
  // ❗ 먼저 제거 후 재추가하면 반복 가능
  cardEl.classList.remove("deal-in");
  void cardEl.offsetWidth; // reflow 강제
  cardEl.classList.add("deal-in");
  playSound("sfx_deal");
}

function flip(cardEl){
  if (cardEl.classList.contains("flipped")){
    cardEl.classList.remove("flipped");
  }
  else{
    cardEl.classList.add("flipped");
  }
  playSound("sfx_cardflip2");
}

function dealAndFlip(cardEl){
  deal(cardEl);
  setTimeout(() => {
    flip(cardEl);
  }, 0);
}

function playSound(id) {
	const src = document.getElementById(id)?.getAttribute("src");
	if (!src) return;

	const audio = new Audio(src);
	audio.play().catch(e => {
		console.warn("⚠️ 사운드 재생 실패:", e);
	});
}

// document.addEventListener('DOMContentLoaded', function(){
//     const ccard = document.getElementById("ccards");
//     for(let i=1; i<6; i++){
//         let card = document.createElement("div");
//         card.id = `ccard${i}_card`;
//         card.class = "card w-8 h-12 rounded-md"
//     }
// }

// <div id="ccard1_card" class="card w-8 h-12 rounded-md bg-white  flex items-center justify-center">
// <div id="ccard1_text" class="text-red-600 font-bold text-sm">A♥</div>
// </div>

// <div id="p1_card1_card" class="card w-14 h-20 rounded-md">
//   <div class="card-inner">
//     <div class="card-front text-red-600 font-bold text-xl">Q♥</div>
//     <div class="card-back">🂠</div>
//   </div>
// </div>
