import React, { useState, useEffect, useRef } from "react";
import "./ChatWindow.css";
import { getAIMessage } from "../api/api";
import { marked } from "marked";

function ChatWindow() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadingState, setLoadingState] = useState("");

  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    setMessages([{
      role: "assistant",
      content: `
Hi there! 👋 

I'm PartSelect's specialized AI assistant, here to help you with:
- **Parts**
- **Models**
- **Compatibility**
- **Installation instructions**
- **Anything else related to PartSelect**

How can I assist you today? Just let me know what you need help with!
      `
    }]);
  }, []);

  const handleSend = async () => {
    if (input.trim() !== "") {
      setMessages(prevMessages => [...prevMessages, { role: "user", content: input }]);
      setInput("");
      setIsLoading(true);
      setLoadingState("Searching for information on partselect.com");

      try {
        setLoadingState("Generating response");
        const response = await getAIMessage(input);
        console.log("Received response:", response);
        if (response && response.response) {
          const { content, videoUrl } = processResponse(response.response);
          setMessages(prevMessages => [
            ...prevMessages,
            { role: "assistant", content },
            ...(videoUrl ? [{ role: "video", content: videoUrl }] : [])
          ]);

          if (response.conversation_ended) {
            alert("This conversation is getting too long. Let's start a new one!");
          }
        } else {
          throw new Error("Invalid response from server");
        }
      } catch (error) {
        console.error('Error getting AI message:', error);
        setMessages(prevMessages => [...prevMessages, { 
          role: "assistant", 
          content: "Sorry, I encountered an error. Please try again or check if the part number is valid." 
        }]);
      } finally {
        setIsLoading(false);
        setLoadingState("");
      }
    }
  };

  const renderMessageContent = (content) => {
    if (content === undefined || content === null) {
      return "Error: No content available";
    }
    try {
      content = content.replace(/{{display:(video|manual|diagram|image)\|(.*?)(\|(.*?))?}}/g, (match, type, url, _, title) => {
        switch(type) {
          case 'video':
            return `<div class="embedded-video">
              <iframe
                width="560"
                height="315"
                src="${url.replace("watch?v=", "embed/")}"
                title="${title || 'Video'}"
                frameBorder="0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              ></iframe>
            </div>`;
          case 'manual':
            return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="manual-link">
              <div class="manual-icon">Manual</div>
              <div class="manual-title">${title || 'Manual'}</div>
            </a>`;
          case 'diagram':
            return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="diagram-link">
              <div class="diagram-icon">Diagram</div>
              <div class="diagram-title">${title || 'Diagram'}</div>
            </a>`;
          case 'image':
            return `<div class="part-image">
              <img src="${url}" alt="${title || 'Image'}" title="${title || 'Image'}" />
            </div>`;
          default:
            return match;
        }
      });
  
      const renderer = new marked.Renderer();
      renderer.link = (href, title, text) => `<a target="_blank" rel="noopener noreferrer" href="${href}" title="${title || ''}">${text}</a>`;
      
      return marked(content, { renderer: renderer, breaks: true, gfm: true });
    } catch (error) {
      console.error('Error parsing message content:', error);
      return "Error parsing message content";
    }
  };

  const renderModelInfo = (modelInfo) => {
    return (
      <div className="model-info">
        <h2>{modelInfo.model_name}</h2>
        <p><a href={modelInfo.model_url} target="_blank" rel="noopener noreferrer">View Model Page</a></p>
        {modelInfo.manuals && modelInfo.manuals.length > 0 && renderModelManuals(modelInfo.manuals)}
        {modelInfo.diagrams && modelInfo.diagrams.length > 0 && renderModelDiagrams(modelInfo.diagrams)}
        {modelInfo.videos && modelInfo.videos.length > 0 && renderModelVideos(modelInfo.videos)}
      </div>
    );
  };

  const renderModelManuals = (manuals) => {
    return (
      <div className="model-manuals">
        <h3>Manuals:</h3>
        <div className="manual-list">
          {manuals.map((manual, index) => (
            <a key={index} href={manual.url} target="_blank" rel="noopener noreferrer" className="manual-item">
              <div className="manual-icon">
                <div className="manual-type">{manual.title.includes('Install') ? 'Install' : 'Manual'}</div>
              </div>
              <div className="manual-title">{manual.title}</div>
            </a>
          ))}
        </div>
      </div>
    );
  };

  const renderModelDiagrams = (diagrams) => {
    return (
      <div className="model-diagrams">
        <h3>Diagrams:</h3>
        <ul>
          {diagrams.map((diagram, index) => (
            <li key={index}>
              <a href={diagram.url} target="_blank" rel="noopener noreferrer">{diagram.title}</a>
            </li>
          ))}
        </ul>
      </div>
    );
  };

  const renderModelVideos = (videos) => {
    return (
      <div className="model-videos">
        <h3>Related Videos:</h3>
        {videos.map((video, index) => (
          <div key={index} className="video-container">
            <iframe
              width="560"
              height="315"
              src={video.url.replace("watch?v=", "embed/")}
              title={video.title}
              frameBorder="0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            ></iframe>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="chat-window">
      <div className="messages-container">
        {messages.map((message, index) => (
          <div key={index} className={`${message.role}-message-container`}>
            {message.role === "video" ? (
              <div className="video-container">
                <iframe
                  width="560"
                  height="315"
                  src={message.content.replace("watch?v=", "embed/")}
                  title="Installation Video"
                  frameBorder="0"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                ></iframe>
              </div>
            ) : (
              <div className={`message ${message.role}-message`}>
                {typeof message.content === 'object' && message.content.type === 'model' ? (
                  renderModelInfo(message.content)
                ) : (
                  <div dangerouslySetInnerHTML={{__html: renderMessageContent(message.content)}} />
                )}
              </div>
            )}
          </div>
        ))}
        {isLoading && (
          <div className="assistant-message-container">
            <div className="message assistant-message">
              <div className="loading-spinner"></div>
              {loadingState}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <div className="input-area">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message..."
          onKeyPress={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              handleSend();
              e.preventDefault();
            }
          }}
        />
        <button className="send-button" onClick={handleSend} disabled={isLoading}>
          Send
        </button>
      </div>
    </div>
  );
}

export default ChatWindow;