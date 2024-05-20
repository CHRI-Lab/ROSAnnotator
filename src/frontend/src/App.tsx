import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";

import { LandingPage } from "./pages/Landing";
import Annotator from "./pages/Annotator";
import MainPage from "./pages/Main";

const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        {/* <Route path="/" element={<Annotator />} /> */}
        <Route path="/" element={<LandingPage />} />

        <Route path="/load" element={<LandingPage />} />
        {/* <Route path="/main" element={<MainPage />} /> */}
        <Route path="/main/:rosBagFile" element={<MainPage />} />
        <Route path="/main/:rosBagFile/:bookListFile" element={<MainPage />} />
      </Routes>
    </Router>
  );
};

export default App;
