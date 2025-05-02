document.addEventListener("DOMContentLoaded", function () {
  const chatForm = document.getElementById("chatForm");
  const questionInput = document.getElementById("question");
  const typing = document.getElementById("typing");
  const loader = document.getElementById("loader");

  if (chatForm) {
    // Handle Send button or form submit
    chatForm.addEventListener("submit", function () {
      if (typing) typing.style.display = "none";
      if (loader) loader.style.display = "block";
    });

    // Handle Enter to submit
    questionInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (typing) typing.style.display = "none";
        if (loader) loader.style.display = "block";
        chatForm.submit();
      }
    });
  }
});
