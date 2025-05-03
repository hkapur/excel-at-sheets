document.addEventListener("DOMContentLoaded", function () {
  const chatForm = document.getElementById("chatForm");
  const questionInput = document.getElementById("question");
  const sendButton = chatForm ? chatForm.querySelector("button[type='submit']") : null;
  const typing = document.getElementById("typing");
  const loader = document.getElementById("loader");
  const chatBox = document.getElementById("chat");

  const suggestedPromptButtons = document.querySelectorAll(".suggested-prompts button");
  const uploadOverlay = document.getElementById("upload-overlay");

  // --- Plot Ideas (Richard branch additions) ---
  const plotIdeasBtn = document.getElementById("plotIdeasBtn");
  const plotIdeasLoader = document.getElementById("plotIdeasLoader");
  const plotIdeasContainer = document.getElementById("plotIdeasContainer");

  if (plotIdeasContainer) {
    plotIdeasContainer.innerHTML = "";
    plotIdeasContainer.style.display = "none";
  }

  // --- End Plot Ideas Section ---

  // Function to show loading state
  function showLoadingState() {
    if (typing) typing.style.display = "none";
    if (loader) {
      loader.style.display = "block";
      loader.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    if (sendButton) sendButton.disabled = true;
    if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;

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

  // Plot Ideas Button Click Handler
  if (plotIdeasBtn) {
    plotIdeasBtn.addEventListener("click", function(e) {
      e.preventDefault();
      window.open('/product_sales_plot', '_blank');
    });
  }

  // Chat form submission
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

  // Excel upload handler
  const excelUploadForm = document.getElementById("uploadForm");
  if (excelUploadForm) {
    excelUploadForm.addEventListener("submit", function () {
      showLoadingState();
    });
  }

  // Receipt upload handler
  const receiptUploadForm = document.getElementById("receiptUploadForm");
  if (receiptUploadForm) {
    receiptUploadForm.addEventListener("submit", function () {
      window.sessionStorage.setItem("showLoader", "true");
      showLoadingState();
    });
  }

  // Auto-scroll chat box
  if (chatBox) {
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  // Final cleanup: hide loader and overlay
  if (loader) loader.style.display = "none";
  if (uploadOverlay) uploadOverlay.style.display = "none";
  if (sendButton) sendButton.disabled = false;
});
