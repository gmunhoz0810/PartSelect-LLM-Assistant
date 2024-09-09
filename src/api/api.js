import axios from 'axios';

const API_URL = 'https://partselect-llm-assistant.onrender.com';

export const getAIMessage = async (userQuery) => {
  try {
    const response = await axios.post(`${API_URL}/query`, { query: userQuery });
    console.log("API response:", response.data);
    return {
      response: response.data.response,
      conversation_ended: response.data.conversation_ended
    };
  } catch (error) {
    console.error('Error fetching AI response:', error);
    console.error('Error details:', error.response?.data);
    throw error;
  }
};

export const resetConversation = async () => {
  try {
    const response = await axios.post(`${API_URL}/reset`);
    if (response.data && response.data.message === "Conversation reset successfully") {
      console.log("Conversation reset successfully");
      return true;
    } else {
      console.warn("Unexpected response from reset endpoint:", response.data);
      return false;
    }
  } catch (error) {
    console.error('Error resetting conversation:', error);
    throw error;
  }
};