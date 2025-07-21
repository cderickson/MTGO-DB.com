function changeHiddenInputsFilter() {
  document.getElementById("dashCard").value = document.getElementById("CardFilter").innerHTML.trim()
  document.getElementById("dashOpponent").value = document.getElementById("OpponentFilter").innerHTML.trim()
  document.getElementById("dashFormat").value = document.getElementById("FormatFilter").innerHTML.trim()
  document.getElementById("dashLimitedFormat").value = document.getElementById("LimitedFormatFilter").innerHTML.trim()
  document.getElementById("dashDeck").value = document.getElementById("DeckFilter").innerHTML.trim()
  document.getElementById("dashOppDeck").value = document.getElementById("OppDeckFilter").innerHTML.trim()
  document.getElementById("dashAction").value = document.getElementById("ActionFilter").innerHTML.trim()
}
function showCardFilter(item) {document.getElementById("CardFilter").innerHTML = item.innerHTML;}
function showOpponentFilter(item) {document.getElementById("OpponentFilter").innerHTML = item.innerHTML;}
function showFormatFilter(item) {
  document.getElementById("FormatFilter").innerHTML = item.innerHTML;
  if (["Cube", "Booster Draft", "Sealed Deck"].includes(item.innerHTML.trim())) {
    document.getElementById("LimitedFormatFilter").removeAttribute("disabled");
  } else {
    document.getElementById("LimitedFormatFilter").innerHTML = "Limited Format ";
    document.getElementById("LimitedFormatFilter").setAttribute("disabled", "disabled");
  }
}
function showLimitedFormatFilter(item) {document.getElementById("LimitedFormatFilter").innerHTML = item.innerHTML;}
function showDeckFilter(item) {document.getElementById("DeckFilter").innerHTML = item.innerHTML;}
function showOppDeckFilter(item) {document.getElementById("OppDeckFilter").innerHTML = item.innerHTML;}
function showActionFilter(item) {document.getElementById("ActionFilter").innerHTML = item.innerHTML;}

$(function(){
  $('#Date1Filter').datepicker({
    format: 'yyyy-mm-dd'
  });
});

$(function(){
  $('#Date2Filter').datepicker({
    format: 'yyyy-mm-dd'
  });
});