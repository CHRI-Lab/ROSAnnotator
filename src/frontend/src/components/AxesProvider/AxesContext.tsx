import React, { useState, createContext, ReactNode } from 'react';

interface BlockProps {
  start: number;
  end: number;
  text?: string;
}

interface AxisData {
  id: number;
  type: string;
  typeName?: string;
  shortcutKey?: string;
  blocks: BlockProps[];
}

interface AxesContextType {
  axes: AxisData[];
  setAxes: React.Dispatch<React.SetStateAction<AxisData[]>>;
}

const AxesContext = createContext<AxesContextType | undefined>(undefined);

interface AxesProviderProps {
  children?: ReactNode;
}

export const AxesProvider: React.FC<AxesProviderProps> = ({ children }) => {
  const [axes, setAxes] = useState<AxisData[]>([]);

  return (
    <AxesContext.Provider value={{ axes, setAxes }}>
      {children}
    </AxesContext.Provider>
  );
};

export default AxesContext;
