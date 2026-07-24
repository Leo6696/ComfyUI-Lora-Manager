import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SidebarManager } from '../../../static/js/components/SidebarManager.js';
import { getStorageItem } from '../../../static/js/utils/storageHelpers.js';

function createManager(activeFolder = 'Anima') {
  const manager = Object.create(SidebarManager.prototype);
  manager.pageType = 'checkpoints';
  manager.selectedPath = activeFolder;
  manager.pageControls = {
    pageState: { activeFolder },
    resetAndReload: vi.fn().mockResolvedValue(undefined),
  };
  manager.updateTreeSelection = vi.fn();
  manager.updateBreadcrumbs = vi.fn();
  manager.updateSidebarHeader = vi.fn();
  return manager;
}

describe('SidebarManager root folder selection', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it.each([null, undefined, ''])(
    'uses no folder filter for the root path %s',
    async (rootPath) => {
      const manager = createManager();

      await manager.selectFolder(rootPath);

      expect(manager.selectedPath).toBe('');
      expect(manager.pageControls.pageState.activeFolder).toBeNull();
      expect(getStorageItem('checkpoints_activeFolder')).toBeNull();
      expect(manager.pageControls.resetAndReload).toHaveBeenCalledOnce();
    },
  );

  it('keeps a real folder as the active filter', async () => {
    const manager = createManager('');

    await manager.selectFolder('Anima/SDXL');

    expect(manager.selectedPath).toBe('Anima/SDXL');
    expect(manager.pageControls.pageState.activeFolder).toBe('Anima/SDXL');
    expect(getStorageItem('checkpoints_activeFolder')).toBe('Anima/SDXL');
  });

  it('migrates a stored empty root filter to no filter', () => {
    localStorage.setItem('lora_manager_checkpoints_activeFolder', '');
    const manager = createManager('');

    manager.restoreSelectedFolder();

    expect(manager.selectedPath).toBe('');
    expect(manager.pageControls.pageState.activeFolder).toBeNull();
    expect(getStorageItem('checkpoints_activeFolder')).toBeNull();
  });

  it('restores a stored child folder unchanged', () => {
    localStorage.setItem('lora_manager_checkpoints_activeFolder', 'Wan');
    const manager = createManager('');

    manager.restoreSelectedFolder();

    expect(manager.selectedPath).toBe('Wan');
    expect(manager.pageControls.pageState.activeFolder).toBe('');
  });
});
