const MENUS = {
    admin: [
        ["Dashboard", "admin-dashboard.html"],
        ["Students", "students.html"],
        ["Faculty", "faculty.html"],
        ["Courses", "courses.html"],
        ["Subjects", "subjects.html"],
        ["Timetable", "timetable.html"],
        ["Attendance", "admin-attendance.html"],
        ["Fees", "fees.html"],
        ["Notices", "notices.html"],
        ["Reports", "reports.html"],
        ["Change Password", "change-password.html"]
    ],
    faculty: [
        ["Dashboard", "faculty-dashboard.html"],
        ["My Subjects", "my-subjects.html"],
        ["Attendance", "mark-attendance.html"],
        ["Results", "enter-marks.html"],
        ["Timetable", "faculty-timetable.html"],
        ["Notices", "notices-view.html"],
        ["Change Password", "change-password.html"]
    ],
    student: [
        ["Dashboard", "student-dashboard.html"],
        ["Attendance", "student-attendance.html"],
        ["Fees", "student-fees.html"],
        ["Timetable", "student-timetable.html"],
        ["Results", "student-results.html"],
        ["Notices", "notices-view.html"],
        ["Change Password", "change-password.html"]
    ]
};

const TITLES = {
    admin: "Admin Portal",
    faculty: "Faculty Portal",
    student: "Student Portal"
};

function logout() {
    localStorage.removeItem("erpUser");
    localStorage.removeItem("erpToken");
    window.location.href = "index.html";
}

(function () {
    // Page ka data-role ek ya zyada roles ho sakta hai, jaise "student,faculty"
    const allowed = (document.body.dataset.role || "").split(",");

    let user = null;
    try {
        user = JSON.parse(localStorage.getItem("erpUser"));
    } catch (e) {}
    const token = localStorage.getItem("erpToken");

    // Login nahi kiya, token nahi hai ya is page ka role nahi hai: wapas login page
    if (!user || !token || !allowed.includes(user.role)) {
        window.location.href = "index.html";
        return;
    }

    const role = user.role;
    const current = location.pathname.split("/").pop();

    const links = MENUS[role].map(function (m) {
        const active = m[1] === current ? ' class="active"' : "";
        return '<a href="' + m[1] + '"' + active + ">" + m[0] + "</a>";
    }).join("");

    document.getElementById("sidebar").innerHTML =
        '<aside class="sidebar">' +
        "<h2>Smart Campus</h2>" +
        '<p class="role">' + TITLES[role] + "</p>" +
        "<nav>" + links + "</nav>" +
        '<button class="logout" onclick="logout()">Logout</button>' +
        "</aside>";

    const name = document.getElementById("userName");
    if (name) name.textContent = user.email;
})();