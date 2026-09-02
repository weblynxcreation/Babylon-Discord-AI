const loginView = document.getElementById("loginView");
const statusView = document.getElementById("statusView");
const loginForm = document.getElementById("loginForm");
const loginError = document.getElementById("loginError");
const userName = document.getElementById("userName");
const linkStatus = document.getElementById("linkStatus");
const companyList = document.getElementById("companyList");
const syncNowBtn = document.getElementById("syncNowBtn");
const logoutBtn = document.getElementById("logoutBtn");

function send(message) {
  return chrome.runtime.sendMessage(message);
}

function timeAgo(ts) {
  if (!ts) return "never";
  const seconds = Math.floor((Date.now() - ts) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  return `${Math.floor(seconds / 60)}m ago`;
}

async function render() {
  const { status } = await send({ type: "GET_STATUS" });

  if (!status?.babylonToken || !status?.babylonUser) {
    loginView.hidden = false;
    statusView.hidden = true;
    return;
  }

  loginView.hidden = true;
  statusView.hidden = false;
  userName.textContent = status.babylonUser.displayName;

  if (status.linkError) {
    linkStatus.textContent = `Link error: ${status.linkError}`;
  } else if (status.linkedCompanies?.length) {
    linkStatus.textContent = `Linked to ${status.linkedCompanies.length} compan${status.linkedCompanies.length === 1 ? "y" : "ies"} - session relayed ${timeAgo(status.lastSessionCookieSyncAt)}`;
  } else {
    linkStatus.textContent = "Not linked yet - visit play.capitalrift.com and open your company dashboard";
  }

  // Just the list of companies now - their actual data (net worth, profit rate, member roster) is
  // confirmed by Babylon's own server poll, not this extension, so there's nothing per-company to
  // show a sync time for anymore. Shows member companies too (not just founded ones) - your session
  // helps keep those fresh too now, since Babylon's poller uses whichever member is currently
  // piloting a company, not just its founder.
  companyList.innerHTML = "";
  for (const c of status.linkedCompanies ?? []) {
    const li = document.createElement("li");
    li.textContent = c.isFounder ? c.name : `${c.name} (member)`;
    companyList.appendChild(li);
  }
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.hidden = true;
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;
  const result = await send({ type: "LOGIN", email, password });
  if (!result.ok) {
    loginError.textContent = result.error;
    loginError.hidden = false;
    return;
  }
  await render();
});

logoutBtn.addEventListener("click", async () => {
  await send({ type: "LOGOUT" });
  await render();
});

syncNowBtn.addEventListener("click", async () => {
  syncNowBtn.textContent = "Relaying...";
  await send({ type: "SYNC_NOW" });
  await render();
  syncNowBtn.textContent = "Relay session now";
});

render();
