document.addEventListener("DOMContentLoaded", function () {
  const chatForm = document.getElementById("chatForm");
  const questionInput = document.getElementById("question");
  const sendButton = chatForm ? chatForm.querySelector("button[type='submit']") : null; // Get send button
  const typing = document.getElementById("typing");
  const loader = document.getElementById("loader");
  const chatBox = document.getElementById("chat");
  const suggestedPromptButtons = document.querySelectorAll(".suggested-prompts button"); // Get buttons
  const plotIdeasBtn = document.getElementById("plotIdeasBtn"); // Get the plot ideas button
  const plotIdeasLoader = document.getElementById("plotIdeasLoader"); // Get the plot ideas loader
  const plotIdeasContainer = document.getElementById("plotIdeasContainer"); // Get the plot ideas container

  // Clear plot ideas container on page load
  if (plotIdeasContainer) {
    plotIdeasContainer.innerHTML = "";
    plotIdeasContainer.style.display = "none";
  }

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

  // --- Plot Ideas Button Click Handler ---
  if (plotIdeasBtn) {
    plotIdeasBtn.addEventListener("click", function(e) {
      e.preventDefault();
      
      // Show loading animation
      if (plotIdeasLoader) {
        plotIdeasLoader.style.display = "block";
      }
      
      // Hide any existing plot ideas
      if (plotIdeasContainer) {
        plotIdeasContainer.innerHTML = "";
        plotIdeasContainer.style.display = "none";
      }
      
      // Fetch plot ideas via AJAX
      fetch('/get_plot_ideas_ajax')
        .then(response => response.json())
        .then(data => {
          // Hide loading animation
          if (plotIdeasLoader) {
            plotIdeasLoader.style.display = "none";
          }
          
          // Display plot ideas
          if (plotIdeasContainer && data.plot_ideas) {
            plotIdeasContainer.innerHTML = "";
            
            const row = document.createElement('div');
            row.className = 'row';
            
            data.plot_ideas.forEach(idea => {
              const col = document.createElement('div');
              col.className = 'col-md-4 mb-3';
              
              const card = document.createElement('div');
              card.className = 'plot-idea-card';
              
              const button = document.createElement('button');
              button.className = 'btn btn-outline-warning btn-sm w-100 mb-2';
              button.textContent = idea.title;
              
              const desc = document.createElement('p');
              desc.className = 'plot-description';
              desc.textContent = idea.description;
              
              card.appendChild(button);
              card.appendChild(desc);
              col.appendChild(card);
              row.appendChild(col);
            });
            
            plotIdeasContainer.appendChild(row);
            plotIdeasContainer.style.display = "block";
          }
        })
        .catch(error => {
          console.error('Error fetching plot ideas:', error);
          // Hide loading animation
          if (plotIdeasLoader) {
            plotIdeasLoader.style.display = "none";
          }
        });
    });
  }
  // --- End Plot Ideas Button Click Handler ---

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
