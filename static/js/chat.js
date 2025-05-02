document.addEventListener("DOMContentLoaded", function () {
  const chatForm = document.getElementById("chatForm");
  const questionInput = document.getElementById("question");
  const typing = document.getElementById("typing");
  const loader = document.getElementById("loader");
  const chatBox = document.getElementById("chat");

  if (chatForm) {
    // Show loader and hide typing on form submission
    chatForm.addEventListener("submit", function () {
      if (typing) typing.style.display = "none";
      if (loader) loader.style.display = "block";
    });

    // Submit form on Enter key press (but allow Shift+Enter for newline)
    questionInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (typing) typing.style.display = "none";
        if (loader) loader.style.display = "block";
        chatForm.submit();
      }
    });
  }

  // Optional: Scroll to latest message on load
  if (chatBox) {
    chatBox.scrollTop = chatBox.scrollHeight;
  }
});
