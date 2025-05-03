document.addEventListener("DOMContentLoaded", function () {
  const chatForm = document.getElementById("chatForm");
  const questionInput = document.getElementById("question");
  const sendButton = chatForm ? chatForm.querySelector("button[type='submit']") : null; // Get send button
  const typing = document.getElementById("typing");
  const loader = document.getElementById("loader");
  const chatBox = document.getElementById("chat");
  const suggestedPromptButtons = document.querySelectorAll(".suggested-prompts button"); // Get buttons

  // Function to show loading state
  function showLoadingState() {
      console.log("showLoadingState called"); // Add console log
      if (typing) typing.style.display = "none";
      if (loader) {
          loader.style.display = "block"; // Make loader visible
          loader.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); // Scroll loader into view
      }
      // if (questionInput) questionInput.disabled = true; // Keep commented out
      if (sendButton) sendButton.disabled = true; // Disable send button
      // Scroll chatbox down too, helps see context
      if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;
  }

  // --- Suggested Prompt Click Handler ---
  suggestedPromptButtons.forEach(button => {
    button.addEventListener("click", function() {
      const promptText = this.getAttribute("data-prompt");
      if (questionInput) {
        questionInput.value = promptText; // Set input value
        questionInput.focus(); // Focus the input field
      }
    });
  });
  // --- End Suggested Prompt Click Handler ---

  if (chatForm) {
    // Show loading state on form submission
    chatForm.addEventListener("submit", function () {
      showLoadingState();
    });

    // Submit form on Enter key press (but allow Shift+Enter for newline)
    questionInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        showLoadingState();
        chatForm.submit();
      }
    });
  }

  // Optional: Scroll to latest message on load
  if (chatBox) {
    chatBox.scrollTop = chatBox.scrollHeight;
  }
});
