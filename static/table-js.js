var match_ids = []

function showP1Arch(item) {document.getElementById("P1ArchButton").innerHTML = item.innerHTML;}
function showP2Arch(item) {document.getElementById("P2ArchButton").innerHTML = item.innerHTML;}
function showFormat(item) {
  document.getElementById("FormatButton").innerHTML = item.innerHTML;
  if (input_options["Limited Formats"].includes(item.innerHTML)){
    document.getElementById("P1ArchButton").disabled = true;
    document.getElementById("P2ArchButton").disabled = true;
    document.getElementById("P1ArchButton").innerHTML = "Limited";
    document.getElementById("P2ArchButton").innerHTML = "Limited";
    document.getElementById("LimitedFormatButton").disabled = false;
    document.getElementById('LimitedFormatButton').innerHTML = "Limited_Format";
    if (item.innerHTML === "Booster Draft"){
      if (!input_options["Booster Draft Formats"].includes(document.getElementById('LimitedFormatButton').innerHTML)){
        document.getElementById('LimitedFormatButton').innerHTML = "Limited_Format"
      }
      if (!input_options["Booster Draft Match Types"].includes(document.getElementById('MatchTypeButton').innerHTML)){
        document.getElementById('MatchTypeButton').innerHTML = "Match_Type"
      }
      document.getElementById('LimitedFormatMenu').innerHTML = "";
      for (var i = 0; i < input_options["Booster Draft Formats"].length; i++){
        document.getElementById("LimitedFormatMenu").innerHTML += '<li><a class="dropdown-item" onclick="showLimitedFormat(this)">'+input_options["Booster Draft Formats"][i]+' </a></li>';
      };
      document.getElementById('MatchTypeMenu').innerHTML = "";
      for (var i = 0; i < input_options["Booster Draft Match Types"].length; i++){
        document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Booster Draft Match Types"][i]+' </a></li>';
      };
    } else if (item.innerHTML === "Sealed Deck"){
      if (!input_options["Sealed Formats"].includes(document.getElementById('LimitedFormatButton').innerHTML)){
        document.getElementById('LimitedFormatButton').innerHTML = "Limited_Format"
      }
      if (!input_options["Sealed Match Types"].includes(document.getElementById('MatchTypeButton').innerHTML)){
        document.getElementById('MatchTypeButton').innerHTML = "Match_Type"
      }
      document.getElementById('LimitedFormatMenu').innerHTML = "";
      for (var i = 0; i < input_options["Sealed Formats"].length; i++){
        document.getElementById("LimitedFormatMenu").innerHTML += '<li><a class="dropdown-item" onclick="showLimitedFormat(this)">'+input_options["Sealed Formats"][i]+' </a></li>';
      };
      document.getElementById('MatchTypeMenu').innerHTML = "";
      for (var i = 0; i < input_options["Sealed Match Types"].length; i++){
        document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Sealed Match Types"][i]+' </a></li>';
      };
    } else if (item.innerHTML === "Cube"){
      if (!input_options["Cube Formats"].includes(document.getElementById('LimitedFormatButton').innerHTML)){
        document.getElementById('LimitedFormatButton').innerHTML = "Limited_Format"
      }
      if (!input_options["Booster Draft Match Types"].includes(document.getElementById('MatchTypeButton').innerHTML)){
        document.getElementById('MatchTypeButton').innerHTML = "Match_Type"
      }
      document.getElementById('LimitedFormatMenu').innerHTML = "";
      for (var i = 0; i < input_options["Cube Formats"].length; i++){
        document.getElementById("LimitedFormatMenu").innerHTML += '<li><a class="dropdown-item" onclick="showLimitedFormat(this)">'+input_options["Cube Formats"][i]+' </a></li>';
      };
      document.getElementById('MatchTypeMenu').innerHTML = "";
      for (var i = 0; i < input_options["Booster Draft Match Types"].length; i++){
        document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Booster Draft Match Types"][i]+' </a></li>';
      };
    };
  } else if (input_options["Constructed Formats"].includes(item.innerHTML)){
    document.getElementById("P1ArchButton").disabled = false;
    document.getElementById("P2ArchButton").disabled = false;
    document.getElementById("P1ArchButton").innerHTML = "P1_Arch";
    document.getElementById("P2ArchButton").innerHTML = "P2_Arch";
    document.getElementById("LimitedFormatButton").disabled = true;
    document.getElementById('LimitedFormatButton').innerHTML = "Limited_Format";
    if (!input_options["Constructed Match Types"].includes(document.getElementById('MatchTypeButton').innerHTML)){
        document.getElementById('MatchTypeButton').innerHTML = "Match_Type"
      }
    document.getElementById('MatchTypeMenu').innerHTML = "";
    for (var i = 0; i < input_options["Constructed Match Types"].length; i++){
      document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Constructed Match Types"][i]+' </a></li>';
    };
  } else if (item.innerHTML === "NA"){
    document.getElementById("P1ArchButton").disabled = false;
    document.getElementById("P2ArchButton").disabled = false;
    document.getElementById("P1ArchButton").innerHTML = "P1_Arch";
    document.getElementById("P2ArchButton").innerHTML = "P2_Arch";
    document.getElementById("LimitedFormatButton").disabled = true;
    document.getElementById('LimitedFormatButton').innerHTML = "Limited_Format";
    document.getElementById('MatchTypeMenu').innerHTML = "";
    for (var i = 0; i < input_options["Constructed Match Types"].length; i++){
      document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Constructed Match Types"][i]+' </a></li>';
    };
    for (var i = 0; i < input_options["Booster Draft Match Types"].length; i++){
      document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Booster Draft Match Types"][i]+' </a></li>';
    };
    for (var i = 0; i < input_options["Sealed Match Types"].length; i++){
      document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Sealed Match Types"][i]+' </a></li>';
    };
  };
  document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">NA </a></li>';
  console.log(item.innerHTML)}
function showLimitedFormat(item) {document.getElementById("LimitedFormatButton").innerHTML = item.innerHTML;}
function showMatchType(item) {document.getElementById("MatchTypeButton").innerHTML = item.innerHTML;}
function changeHiddenInputsMulti() {
  var match_ids = "";
  $(".active").each(function() {
      match_ids = match_ids + "," + ($(this).text().trim().replace(/\s\s+/g, ' ').split(" ")[0]);
  });
  match_ids = match_ids.substring(1)
  console.log(match_ids)
  document.getElementById("Match_ID_Multi").value = match_ids
  document.getElementById("FieldToChangeMulti").value = document.getElementById("FieldToChangeButton").innerHTML.trim()
  document.getElementById("P1ArchMulti").value = document.getElementById("P1ArchButtonMulti").innerHTML.trim()
  document.getElementById("P2ArchMulti").value = document.getElementById("P2ArchButtonMulti").innerHTML.trim()
  document.getElementById("FormatMulti").value = document.getElementById("FormatButtonMulti").innerHTML.trim()
  document.getElementById("Limited_FormatMulti").value = document.getElementById("LimitedFormatButtonMulti").innerHTML.trim()
  document.getElementById("Match_TypeMulti").value = document.getElementById("MatchTypeButtonMulti").innerHTML.trim()
}
function changeHiddenInputsIgnored() {
  var match_ids = "";
  $(".active").each(function() {
      match_ids = match_ids + "," + ($(this).text().trim().replace(/\s\s+/g, ' ').split(" ")[0]);
  });
  match_ids = match_ids.substring(1)
  console.log(match_ids)
  document.getElementById("Ignored_Match_ID_Multi").value = match_ids
}
function changeHiddenInputs() {
  document.getElementById("Match_ID").value = document.getElementById("ReviseModalLabel").innerHTML.trim().split(" - ")[1]
  if (document.getElementById("P1ArchButton").innerHTML.trim() === "P1_Arch"){
    document.getElementById("P1Arch").value = "NA"
  } else{
    document.getElementById("P1Arch").value = document.getElementById("P1ArchButton").innerHTML.trim()
  }
  if (document.getElementById("P2ArchButton").innerHTML.trim() === "P2_Arch"){
    document.getElementById("P2Arch").value = "NA"
  } else{
    document.getElementById("P2Arch").value = document.getElementById("P2ArchButton").innerHTML.trim()
  }
  if (document.getElementById("FormatButton").innerHTML.trim() === "Format"){
    document.getElementById("Format").value = "NA"
  } else{
    document.getElementById("Format").value = document.getElementById("FormatButton").innerHTML.trim()
  }
  if (document.getElementById("LimitedFormatButton").innerHTML.trim() === "Limited_Format"){
    document.getElementById("Limited_Format").value = "NA"
  } else{
    document.getElementById("Limited_Format").value = document.getElementById("LimitedFormatButton").innerHTML.trim()
  }
  if (document.getElementById("MatchTypeButton").innerHTML.trim() === "Match_Type"){
    document.getElementById("Match_Type").value = "NA"
  } else{
    document.getElementById("Match_Type").value = document.getElementById("MatchTypeButton").innerHTML.trim()
  }
}
function showP1Field(item) {
  document.getElementById("FieldToChangeButton").innerHTML = item.innerHTML;
  document.getElementById("P1ArchCol1").style.display = 'block'
  document.getElementById("P1ArchCol2").style.display = 'block'
  document.getElementById("P1SubarchCol1").style.display = 'block'
  document.getElementById("P1SubarchCol2").style.display = 'block'
  document.getElementById("P2ArchCol1").style.display = 'none'
  document.getElementById("P2ArchCol2").style.display = 'none'
  document.getElementById("P2SubarchCol1").style.display = 'none'
  document.getElementById("P2SubarchCol2").style.display = 'none'
  document.getElementById("FormatCol1").style.display = 'none'
  document.getElementById("FormatCol2").style.display = 'none'
  document.getElementById("LimitedFormatCol1").style.display = 'none'
  document.getElementById("LimitedFormatCol2").style.display = 'none'
  document.getElementById("MatchTypeCol1").style.display = 'none'
  document.getElementById("MatchTypeCol2").style.display = 'none'
  document.getElementById("P1DeckBR").style.display = "inline";
  document.getElementById("P2DeckBR").style.display = "none";
  document.getElementById("FormatBR").style.display = "none";
}
function showP2Field(item) {
  document.getElementById("FieldToChangeButton").innerHTML = item.innerHTML;
  document.getElementById("P1ArchCol1").style.display = 'none'
  document.getElementById("P1ArchCol2").style.display = 'none'
  document.getElementById("P1SubarchCol1").style.display = 'none'
  document.getElementById("P1SubarchCol2").style.display = 'none'
  document.getElementById("P2ArchCol1").style.display = 'block'
  document.getElementById("P2ArchCol2").style.display = 'block'
  document.getElementById("P2SubarchCol1").style.display = 'block'
  document.getElementById("P2SubarchCol2").style.display = 'block'
  document.getElementById("FormatCol1").style.display = 'none'
  document.getElementById("FormatCol2").style.display = 'none'
  document.getElementById("LimitedFormatCol1").style.display = 'none'
  document.getElementById("LimitedFormatCol2").style.display = 'none'
  document.getElementById("MatchTypeCol1").style.display = 'none'
  document.getElementById("MatchTypeCol2").style.display = 'none'
  document.getElementById("P1DeckBR").style.display = "none";
  document.getElementById("P2DeckBR").style.display = "inline";
  document.getElementById("FormatBR").style.display = "none";
}
function showFormatField(item) {
  document.getElementById("FieldToChangeButton").innerHTML = item.innerHTML;
  document.getElementById("P1ArchCol1").style.display = 'none'
  document.getElementById("P1ArchCol2").style.display = 'none'
  document.getElementById("P1SubarchCol1").style.display = 'none'
  document.getElementById("P1SubarchCol2").style.display = 'none'
  document.getElementById("P2ArchCol1").style.display = 'none'
  document.getElementById("P2ArchCol2").style.display = 'none'
  document.getElementById("P2SubarchCol1").style.display = 'none'
  document.getElementById("P2SubarchCol2").style.display = 'none'
  document.getElementById("FormatCol1").style.display = 'block'
  document.getElementById("FormatCol2").style.display = 'block'
  document.getElementById("LimitedFormatCol1").style.display = 'block'
  document.getElementById("LimitedFormatCol2").style.display = 'block'
  document.getElementById("MatchTypeCol1").style.display = 'none'
  document.getElementById("MatchTypeCol2").style.display = 'none'
  document.getElementById("P1DeckBR").style.display = "none";
  document.getElementById("P2DeckBR").style.display = "none";
  document.getElementById("FormatBR").style.display = "inline";
}
function showMatchTypeField(item) {
  document.getElementById("FieldToChangeButton").innerHTML = item.innerHTML;
  document.getElementById("P1ArchCol1").style.display = 'none'
  document.getElementById("P1ArchCol2").style.display = 'none'
  document.getElementById("P1SubarchCol1").style.display = 'none'
  document.getElementById("P1SubarchCol2").style.display = 'none'
  document.getElementById("P2ArchCol1").style.display = 'none'
  document.getElementById("P2ArchCol2").style.display = 'none'
  document.getElementById("P2SubarchCol1").style.display = 'none'
  document.getElementById("P2SubarchCol2").style.display = 'none'
  document.getElementById("FormatCol1").style.display = 'none'
  document.getElementById("FormatCol2").style.display = 'none'
  document.getElementById("LimitedFormatCol1").style.display = 'none'
  document.getElementById("LimitedFormatCol2").style.display = 'none'
  document.getElementById("MatchTypeCol1").style.display = 'block'
  document.getElementById("MatchTypeCol2").style.display = 'block'
  document.getElementById("P1DeckBR").style.display = "none";
  document.getElementById("P2DeckBR").style.display = "none";
  document.getElementById("FormatBR").style.display = "none";
}
function showP1ArchMulti(item) {document.getElementById("P1ArchButtonMulti").innerHTML = item.innerHTML;}
function showP2ArchMulti(item) {document.getElementById("P2ArchButtonMulti").innerHTML = item.innerHTML;}
function showFormatMulti(item) {
  document.getElementById("FormatButtonMulti").innerHTML = item.innerHTML;
  if (input_options["Constructed Formats"].includes(item.innerHTML)){
    document.getElementById("LimitedFormatButtonMulti").innerHTML = "NA"
    document.getElementById("LimitedFormatButtonMulti").disabled = true
  } else if (item.innerHTML === "NA"){
    document.getElementById("LimitedFormatButtonMulti").innerHTML = "NA"
    document.getElementById("LimitedFormatButtonMulti").disabled = true
  } else{
    document.getElementById("LimitedFormatButtonMulti").innerHTML = "NA"
    document.getElementById("LimitedFormatButtonMulti").disabled = false
    if (item.innerHTML === "Booster Draft"){
      document.getElementById('LimitedFormatMenuMulti').innerHTML = "";
      for (var i = 0; i < input_options["Booster Draft Formats"].length; i++){
        document.getElementById("LimitedFormatMenuMulti").innerHTML += '<li><a class="dropdown-item" onclick="showLimitedFormatMulti(this)">'+input_options["Booster Draft Formats"][i]+' </a></li>';
      };
    } else if (item.innerHTML === "Sealed Deck"){
      document.getElementById('LimitedFormatMenuMulti').innerHTML = "";
      for (var i = 0; i < input_options["Sealed Formats"].length; i++){
        document.getElementById("LimitedFormatMenuMulti").innerHTML += '<li><a class="dropdown-item" onclick="showLimitedFormatMulti(this)">'+input_options["Sealed Formats"][i]+' </a></li>';
      };
    } else if (item.innerHTML === "Cube"){
      document.getElementById('LimitedFormatMenuMulti').innerHTML = "";
      for (var i = 0; i < input_options["Cube Formats"].length; i++){
        document.getElementById("LimitedFormatMenuMulti").innerHTML += '<li><a class="dropdown-item" onclick="showLimitedFormatMulti(this)">'+input_options["Cube Formats"][i]+' </a></li>';
      };
    }
  };
};
function showLimitedFormatMulti(item) {document.getElementById("LimitedFormatButtonMulti").innerHTML = item.innerHTML;}
function showMatchTypeMulti(item) {document.getElementById("MatchTypeButtonMulti").innerHTML = item.innerHTML;}

let input_options;
window.onload = function(){
  fetch('/input_options').then(function(response){
    response.json().then(function(data){
      input_options = data;
      for (var i = 0; i < data["Archetypes"].length; i++){
        document.getElementById("P1ArchMenu").innerHTML += '<li><a class="dropdown-item" onclick="showP1Arch(this)">'+data["Archetypes"][i]+'</a></li>';
        document.getElementById("P2ArchMenu").innerHTML += '<li><a class="dropdown-item" onclick="showP2Arch(this)">'+data["Archetypes"][i]+'</a></li>';
        document.getElementById("P1ArchMenuMulti").innerHTML += '<li><a class="dropdown-item" onclick="showP1ArchMulti(this)">'+data["Archetypes"][i]+'</a></li>';
        document.getElementById("P2ArchMenuMulti").innerHTML += '<li><a class="dropdown-item" onclick="showP2ArchMulti(this)">'+data["Archetypes"][i]+'</a></li>';
      };
      for (var i = 0; i < data["Constructed Formats"].length; i++){
        document.getElementById("FormatMenuMulti").innerHTML += '<li><a class="dropdown-item" onclick="showFormatMulti(this)">'+data["Constructed Formats"][i]+'</a></li>';
        document.getElementById("FormatMenu").innerHTML += '<li><a class="dropdown-item" onclick="showFormat(this)">'+data["Constructed Formats"][i]+'</a></li>';
      };
      for (var i = 0; i < data["Limited Formats"].length; i++){
        document.getElementById("FormatMenuMulti").innerHTML += '<li><a class="dropdown-item" onclick="showFormatMulti(this)">'+data["Limited Formats"][i]+'</a></li>';
        document.getElementById("FormatMenu").innerHTML += '<li><a class="dropdown-item" onclick="showFormat(this)">'+data["Limited Formats"][i]+'</a></li>';
      };
      for (var i = 0; i < data["Constructed Match Types"].length; i++){
        document.getElementById("MatchTypeMenuMulti").innerHTML += '<li><a class="dropdown-item" onclick="showMatchTypeMulti(this)">'+data["Constructed Match Types"][i]+'</a></li>';
        document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Constructed Match Types"][i]+'</a></li>';
      };
      for (var i = 0; i < data["Booster Draft Match Types"].length; i++){
        document.getElementById("MatchTypeMenuMulti").innerHTML += '<li><a class="dropdown-item" onclick="showMatchTypeMulti(this)">'+data["Booster Draft Match Types"][i]+'</a></li>';
        document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Booster Draft Match Types"][i]+'</a></li>';
      };
      for (var i = 0; i < data["Sealed Match Types"].length; i++){
        document.getElementById("MatchTypeMenuMulti").innerHTML += '<li><a class="dropdown-item" onclick="showMatchTypeMulti(this)">'+data["Sealed Match Types"][i]+'</a></li>';
        document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Sealed Match Types"][i]+'</a></li>';
      };
      document.getElementById("FormatMenu").innerHTML += '<li><a class="dropdown-item" onclick="showFormat(this)">NA</a></li>';
      document.getElementById("FormatMenuMulti").innerHTML += '<li><a class="dropdown-item" onclick="showFormatMulti(this)">NA</a></li>';
      document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">NA</a></li>';
      document.getElementById("MatchTypeMenuMulti").innerHTML += '<li><a class="dropdown-item" onclick="showMatchTypeMulti(this)">NA</a></li>';
    });
  });     
};

function removeHidden(label) {
  document.getElementById("removeType").value = label;
  document.getElementById("removeMatchId").value = match_ids;
  return true;
};

window.addEventListener("load", function() {
  var reviseButton = document.getElementById("ReviseButton")
  var removeButton = document.getElementById("RemoveButton")
  if (reviseButton) {
    reviseButton.setAttribute("disabled", "disabled");
  }
  if (removeButton) {
    removeButton.setAttribute("disabled", "disabled");
  }
});

function getRange(start, end) {
  var result = [];

  if (start <= end) {
    for (var i = start; i <= end; i++) {
      result.push(i);
    }
  } else {
    for (var i = start; i >= end; i--) {
      result.push(i);
    }
  }
  return result;
};

$(document).ready(function(){
  var reviseButton = document.getElementById("ReviseButton")
  var removeButton = document.getElementById("RemoveButton")
  var table_name = document.getElementById("tname").value
  var toRevise = [];
  var tableRows = document.querySelectorAll('.jsTableRow');
  lastClickedRow = ""
  shiftClickedRow = ""
  range = []
  
  $(".jsTableRow").dblclick(function(){
    var str = $(this).text().trim().replace(/\s\s+/g, ' ').split(" ")
    var table = $("h3").text().split(" ")[0]
    if (table == "Matches"){
      window.location.href = '/table/games/'+str[0]+'/0'
    } else if (table == "Games"){
      window.location.href = '/table/plays/'+str[0]+'/'+str[3]
    } else if (table == "Drafts"){
      window.location.href = '/table/picks/'+str[0]+'/0'
    }
  });

  $(".jsTableRow").click(function(event){
    if (event.shiftKey) {
      shiftClickedRow = $(this).attr("id")
      if (lastClickedRow !== "") {
        range = getRange(parseInt(lastClickedRow.match(/\d+/)[0]), parseInt(shiftClickedRow.match(/\d+/)[0]))
        for (var i = 0; i < range.length; i++) {
          for (var j = 0; j < tableRows.length; j++) {
            if (tableRows[j].id === "row" + range[i]) {
              tableRows[j].className = "active"
            }
          }
        }
      }
    } else if (event.ctrlKey) {
      console.log($(this))
      if ($(this).hasClass("active")) {
        $(this).removeClass("active");
      } else {
        $(this).addClass("active");
      }
    } else {
      lastClickedRow = $(this).attr("id");
      for (var i = 0; i < tableRows.length; i++) {
        tableRows[i].className = ""
      }
      $(this).toggleClass("active");
    }

    var myarray = [];
    $(".active").each(function() {
      myarray.push($(this).text().trim().replace(/\s\s+/g, ' ').split(" "));
    });
    match_ids = myarray.map(innerArray => innerArray[0]);
    console.log(match_ids)
    if (reviseButton && removeButton) {
      if (myarray.length === 1){
        reviseButton.disabled = false;
        removeButton.disabled = false;
        reviseButton.setAttribute("data-bs-target", "#ReviseModal");
      } else if (myarray.length > 1){
        reviseButton.disabled = false;
        removeButton.disabled = false;
        reviseButton.setAttribute("data-bs-target", "#ReviseMultiModal");
      } else if (myarray.length === 0){
        reviseButton.disabled = true;
        removeButton.disabled = true;
      };
    };

    $(".active").each(function() {
        toRevise = $(this).text().trim().replace(/\s\s+/g, ' ').split(" ");
    });
    console.log(toRevise)
    if ((toRevise.length > 0) && (table_name == "matches")) {
      fetch('/values/'+toRevise[0], {headers: {'X-Requested-By': 'MTGO-Tracker'}}).then(function(response){
        response.json().then(function(data){
          console.log(data)
          document.getElementById("ReviseModalLabel").innerHTML = 'Revise Record - ' + data.match_id;
          document.getElementById("ModalDate").innerHTML = '<center><b>Date Played:</b> ' + data.date + '</center>';
          if (data.p1 == data.casting_player1) {
            document.getElementById("ModalP1").innerHTML = '<b>P1: ' + data.casting_player1 + '</b>';
            document.getElementById("ModalP2").innerHTML = '<b>P2: ' + data.casting_player2 + '</b>';
            document.getElementById("RevisePlays1").innerHTML = data.plays1;
            document.getElementById("RevisePlays2").innerHTML = data.plays2;
            document.getElementById("ReviseLands1").innerHTML = data.lands1;
            document.getElementById("ReviseLands2").innerHTML = data.lands2;
          } else {
            document.getElementById("ModalP1").innerHTML = '<b>P1: ' + data.casting_player2 + '</b>';
            document.getElementById("ModalP2").innerHTML = '<b>P2: ' + data.casting_player1 + '</b>';
            document.getElementById("RevisePlays1").innerHTML = data.plays2;
            document.getElementById("RevisePlays2").innerHTML = data.plays1;
            document.getElementById("ReviseLands1").innerHTML = data.lands2;
            document.getElementById("ReviseLands2").innerHTML = data.lands1;
          }
          if (data.p1_arch != "NA"){
            document.getElementById('P1ArchButton').innerHTML = data.p1_arch;
          } else{
            document.getElementById('P1ArchButton').innerHTML = "P1_Arch";
          };
          if (data.p2_arch != "NA"){
            document.getElementById('P2ArchButton').innerHTML = data.p2_arch;
          } else{
            document.getElementById('P2ArchButton').innerHTML = "P2_Arch";
          };
          if (data.p1_subarch != "NA"){
            document.getElementById('P1_Subarch').value = data.p1_subarch;
          } else{
            document.getElementById('P1_Subarch').value = "NA";
          };
          if (data.p2_subarch != "NA"){
            document.getElementById('P2_Subarch').value = data.p2_subarch;
          } else{
            document.getElementById('P2_Subarch').value = "NA";
          };
          if (data.format != "NA"){
            document.getElementById('FormatButton').innerHTML = data.format;
            if (input_options["Constructed Formats"].includes(data.format)){
              document.getElementById('LimitedFormatButton').innerHTML = "Limited_Format";
              document.getElementById('LimitedFormatButton').disabled = true;
              document.getElementById('MatchTypeMenu').innerHTML = "";
              for (var i = 0; i < input_options["Constructed Match Types"].length; i++){
                document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Constructed Match Types"][i]+' </a></li>';
              };
            };
            if (data.format === "Booster Draft"){
              document.getElementById('LimitedFormatButton').innerHTML = "Limited_Format";
              document.getElementById('LimitedFormatButton').disabled = false;
              document.getElementById('LimitedFormatMenu').innerHTML = "";
              for (var i = 0; i < input_options["Booster Draft Formats"].length; i++){
                document.getElementById("LimitedFormatMenu").innerHTML += '<li><a class="dropdown-item" onclick="showLimitedFormat(this)">'+input_options["Booster Draft Formats"][i]+' </a></li>';
              };
              document.getElementById('MatchTypeMenu').innerHTML = "";
              for (var i = 0; i < input_options["Booster Draft Match Types"].length; i++){
                document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Booster Draft Match Types"][i]+' </a></li>';
              };
            };
            if (data.format === "Sealed Deck"){
              document.getElementById('LimitedFormatButton').innerHTML = "Limited_Format";
              document.getElementById('LimitedFormatButton').disabled = false;
              document.getElementById('LimitedFormatMenu').innerHTML = "";
              for (var i = 0; i < input_options["Sealed Formats"].length; i++){
                document.getElementById("LimitedFormatMenu").innerHTML += '<li><a class="dropdown-item" onclick="showLimitedFormat(this)">'+input_options["Sealed Formats"][i]+' </a></li>';
              };
              document.getElementById('MatchTypeMenu').innerHTML = "";
              for (var i = 0; i < input_options["Sealed Match Types"].length; i++){
                document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Sealed Match Types"][i]+' </a></li>';
              };
            };
            if (data.format === "Cube"){
              document.getElementById('LimitedFormatButton').innerHTML = "Limited_Format";
              document.getElementById('LimitedFormatButton').disabled = false;
              document.getElementById('LimitedFormatMenu').innerHTML = "";
              for (var i = 0; i < input_options["Cube Formats"].length; i++){
                document.getElementById("LimitedFormatMenu").innerHTML += '<li><a class="dropdown-item" onclick="showLimitedFormat(this)">'+input_options["Cube Formats"][i]+' </a></li>';
              };
              document.getElementById('MatchTypeMenu').innerHTML = "";
              for (var i = 0; i < input_options["Booster Draft Match Types"].length; i++){
                document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">'+input_options["Booster Draft Match Types"][i]+' </a></li>';
              };
            };
            document.getElementById("MatchTypeMenu").innerHTML += '<li><a class="dropdown-item" onclick="showMatchType(this)">NA </a></li>';
          } else{
            document.getElementById('FormatButton').innerHTML = "Format";
          };
          if (data.limited_format != "NA"){
            document.getElementById('LimitedFormatButton').innerHTML = data.limited_format;
          } else{
            document.getElementById('LimitedFormatButton').innerHTML = "Limited_Format";
          };
          if (data.match_type != "NA"){
            document.getElementById('MatchTypeButton').innerHTML = data.match_type;
          } else{
            document.getElementById('MatchTypeButton').innerHTML = "Match_Type";
          };
          if (document.getElementById('P1ArchButton').innerHTML == 'Limited'){
            document.getElementById("P1ArchButton").disabled = true;
          };
          if (document.getElementById('P2ArchButton').innerHTML == 'Limited'){
            document.getElementById("P2ArchButton").disabled = true;
          };
        });
      });
    };

  })
})