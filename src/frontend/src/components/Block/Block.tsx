import React from 'react';
import { styled } from '@mui/system';

interface BlockProps {
  block: { start: number; end: number };
  duration: number;
  isSelected: boolean;
  onSelect: () => void;
}

const NewBlock = styled('div')(({ theme }) => ({
  position: 'absolute',
  height: '100%',
  backgroundColor: theme.palette.action.selected,
}));

const Block: React.FC<BlockProps> = ({ block, duration, isSelected, onSelect }) => {
  return (
    <NewBlock
      onClick={onSelect}
      style={{
        left: `${(block.start / duration) * 100}%`,
        width: `${((block.end - block.start) / duration) * 100}%`,
        backgroundColor: isSelected ? 'red' : 'grey',
      }}
    />
  );
};

export default Block;
