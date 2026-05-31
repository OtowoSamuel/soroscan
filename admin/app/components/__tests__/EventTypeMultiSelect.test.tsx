import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EventTypeMultiSelect } from '../EventTypeMultiSelect';

describe('EventTypeMultiSelect', () => {
  const defaultProps = {
    selected: [] as string[],
    onChange: vi.fn(),
  };

  it('renders all event type groups', () => {
    render(<EventTypeMultiSelect {...defaultProps} />);
    
    expect(screen.getByText('Trading')).toBeInTheDocument();
    expect(screen.getByText('Vault')).toBeInTheDocument();
    expect(screen.getByText('Staking')).toBeInTheDocument();
    expect(screen.getByText('Oracle')).toBeInTheDocument();
    expect(screen.getByText('Governance')).toBeInTheDocument();
  });

  it('renders search input', () => {
    render(<EventTypeMultiSelect {...defaultProps} />);
    
    expect(screen.getByPlaceholderText('Search event types...')).toBeInTheDocument();
  });

  it('renders select all/none buttons', () => {
    render(<EventTypeMultiSelect {...defaultProps} />);
    
    expect(screen.getByText('Select All')).toBeInTheDocument();
    expect(screen.getByText('Select None')).toBeInTheDocument();
  });

  it('calls onChange when checkbox is toggled', () => {
    const onChange = vi.fn();
    render(<EventTypeMultiSelect {...defaultProps} onChange={onChange} />);
    
    const checkbox = screen.getByRole('checkbox', { name: /SWAP COMPLETE/i });
    fireEvent.click(checkbox);
    
    expect(onChange).toHaveBeenCalledWith(['SWAP_COMPLETE']);
  });

  it('handles ALL selection toggle', () => {
    const onChange = vi.fn();
    render(<EventTypeMultiSelect {...defaultProps} onChange={onChange} />);
    
    const allCheckbox = screen.getByRole('checkbox', { name: /ALL/i });
    fireEvent.click(allCheckbox);
    
    expect(onChange).toHaveBeenCalledWith(['ALL']);
  });

  it('filters event types by search', () => {
    const onChange = vi.fn();
    render(<EventTypeMultiSelect {...defaultProps} onChange={onChange} />);
    
    const searchInput = screen.getByPlaceholderText('Search event types...');
    fireEvent.change(searchInput, { target: { value: 'swap' } });
    
    expect(screen.getByText(/SWAP COMPLETE/i)).toBeInTheDocument();
    expect(screen.queryByText(/VAULT DEPOSIT/i)).not.toBeInTheDocument();
  });

  it('displays selection summary', () => {
    const { rerender } = render(
      <EventTypeMultiSelect {...defaultProps} selected={[]} />
    );
    
    expect(screen.getByText('No event types selected')).toBeInTheDocument();
    
    rerender(
      <EventTypeMultiSelect {...defaultProps} selected={['SWAP_COMPLETE', 'LIQUIDITY_ADD']} />
    );
    
    expect(screen.getByText('2 event types selected')).toBeInTheDocument();
    
    rerender(
      <EventTypeMultiSelect {...defaultProps} selected={['ALL']} />
    );
    
    expect(screen.getByText('All event types selected')).toBeInTheDocument();
  });

  it('handles select all button', () => {
    const onChange = vi.fn();
    render(<EventTypeMultiSelect {...defaultProps} onChange={onChange} />);
    
    fireEvent.click(screen.getByText('Select All'));
    
    expect(onChange).toHaveBeenCalled();
    const calledWith = onChange.mock.calls[0][0];
    expect(calledWith).toContain('ALL');
  });

  it('handles select none button', () => {
    const onChange = vi.fn();
    render(
      <EventTypeMultiSelect 
        {...defaultProps} 
        onChange={onChange} 
        selected={['SWAP_COMPLETE']} 
      />
    );
    
    fireEvent.click(screen.getByText('Select None'));
    
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it('respects disabled prop', () => {
    const onChange = vi.fn();
    render(<EventTypeMultiSelect {...defaultProps} onChange={onChange} disabled />);
    
    const searchInput = screen.getByPlaceholderText('Search event types...');
    expect(searchInput).toBeDisabled();
    
    const checkbox = screen.getByRole('checkbox', { name: /SWAP COMPLETE/i });
    expect(checkbox).toBeDisabled();
    
    fireEvent.click(checkbox);
    expect(onChange).not.toHaveBeenCalled();
  });
});