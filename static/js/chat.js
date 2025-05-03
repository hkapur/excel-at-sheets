document.addEventListener("DOMContentLoaded", function () {
  const chatForm = document.getElementById("chatForm");
  const questionInput = document.getElementById("question");
  const sendButton = chatForm ? chatForm.querySelector("button[type='submit']") : null;
  const typing = document.getElementById("typing");
  const loader = document.getElementById("loader");
  const chatBox = document.getElementById("chat");
  const suggestedPromptButtons = document.querySelectorAll(".suggested-prompts button");
  const uploadOverlay = document.getElementById("upload-overlay");

  // Function to show loading state
  function showLoadingState() {
    console.log("showLoadingState called");
    if (typing) typing.style.display = "none";
    if (loader) {
      loader.style.display = "block";
      loader.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    if (sendButton) sendButton.disabled = true;
    if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;

    // Show overlay on upload section
    if (uploadOverlay) {
      uploadOverlay.style.display = "flex";
    }
  }

  // Suggested Prompt Click Handler
  suggestedPromptButtons.forEach(button => {
    button.addEventListener("click", function () {
      const promptText = this.getAttribute("data-prompt");
      if (questionInput) {
        questionInput.value = promptText;
        questionInput.focus();
      }
    });
  });

  if (chatForm) {
    chatForm.addEventListener("submit", function () {
      showLoadingState();
    });

    questionInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        showLoadingState();
        chatForm.submit();
      }
    });
  }

  // Handle Excel file upload
  const excelUploadForm = document.getElementById("uploadForm");
  if (excelUploadForm) {
    excelUploadForm.addEventListener("submit", function () {
      showLoadingState();
    });
  }

  // Handle PDF receipt upload with persistent loader
  const receiptUploadForm = document.getElementById("receiptUploadForm");
  if (receiptUploadForm) {
    receiptUploadForm.addEventListener("submit", function () {
      window.sessionStorage.setItem("showLoader", "true");
      showLoadingState();
    });
  }

  // Scroll to latest message on load
  if (chatBox) {
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  // ✅ Final cleanup: hide loader and overlay
  if (loader) loader.style.display = "none";
  if (uploadOverlay) uploadOverlay.style.display = "none";
  if (sendButton) sendButton.disabled = false;
});
