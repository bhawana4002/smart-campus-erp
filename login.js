const PAGES = {
    student: "student-dashboard.html",
    faculty: "faculty-dashboard.html",
    admin: "admin-dashboard.html"
};

document.getElementById("loginForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    const role = document.getElementById("role").value;
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const message = document.getElementById("message");

    message.style.color = "#dc2626";

    try {
        const response = await fetch("http://127.0.0.1:5001/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ role: role, email: email, password: password })
        });
        const data = await response.json();

        if (!response.ok || !data.ok) {
            message.textContent = data.message || "Login nahi ho paya.";
            return;
        }

        localStorage.setItem("erpUser", JSON.stringify(data.user));
        localStorage.setItem("erpToken", data.token);
        window.location.href = PAGES[data.user.role];
    } catch (err) {
        message.textContent = "Server se connect nahi ho paya. Backend chalu hai?";
    }
});