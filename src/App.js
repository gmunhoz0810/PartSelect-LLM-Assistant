import React, { useState } from "react";
import "./App.css";
import ChatWindow from "./components/ChatWindow";
import { resetConversation } from "./api/api";

function App() {
  const [key, setKey] = useState(0);

  const handleResetConversation = async () => {
    try {
      await resetConversation();
      setKey(prevKey => prevKey + 1);
    } catch (error) {
      console.error('Error resetting conversation:', error);
    }
  };

  return (
    <div className="App">
      <header className="app-header">
        <span className="title">Instalily Case Study</span>
        <button className="new-chat-button" onClick={handleResetConversation}>
          New Chat
        </button>
      </header>
      <main className="app-main">
        <ChatWindow key={key} />
      </main>
    </div>
  );
}

export default App;