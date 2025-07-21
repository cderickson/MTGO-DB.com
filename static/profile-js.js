function editProfile() {
  document.getElementById("CancelProfileButton").style.display = "block";
  //document.getElementById("AddNewUsernameButton").style.display = "block";
  document.getElementById("EditProfileButton").style.display = "none";
  document.getElementById("SaveProfileButton").style.display = "block";
  //document.getElementById("ProfileNameDisplay").style.display = "none";
  //document.getElementById("ProfileNameInput").style.display = "block";
  //document.getElementById("ProfileEmailDisplay").style.display = "none";
  //document.getElementById("ProfileEmailInput").style.display = "block";
  document.getElementById("ProfileUsernameDisplay").style.display = "none";
  document.getElementById("ProfileUsernameInput").style.display = "block";
};

function addNewUsername() {
  document.getElementById("ProfileUsernameInput").innerHTML += '<div class="col mb-1"><div class="input-group input-group"><input type="text" class="form-control" name="ProfileUsernameInputText" placeholder="Username" value=""></div></div>'
};

function cancelEditProfile() {
  window.location.replace('/profile');
};

function loadIgnored() {
  fetch('/ignored', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    }
  })
};

function editUserDB() {
  const data = { 
    //ProfileEmailInputText: document.getElementsByName("ProfileEmailInputText")[0].value, 
    //ProfileNameInputText: document.getElementsByName("ProfileNameInputText")[0].value,
    ProfileUsernameInputText: document.getElementsByName("ProfileUsernameInputText")[0].value,
  };

  fetch('/edit_profile', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  }).then(response => {
    location.reload();
  })
};