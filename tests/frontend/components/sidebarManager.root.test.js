import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SidebarManager } from '../../../static/js/components/SidebarManager.js';
import { getStorageItem } from '../../../static/js/utils/storageHelpers.js';

function createManager(activeFolder = 'Anima') {
  const manager = Object.create(SidebarManager.prototype);
  manager.pageType = 'checkpoints';
  manager.selectedPath = activeFolder;
  manager.pageControls = {
    pageState: { activeFolder, activeFolderRoot: null },
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
    expect(manager.pageControls.pageState.activeFolderRoot).toBeNull();
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
    expect(manager.pageControls.pageState.activeFolder).toBe('Wan');
  });

  it('maps a drive-prefixed UI folder to its matching model root', async () => {
    const manager = createManager('');
    manager.folderSelectionMap = new Map([
      ['D:/Krea 2', { path: 'Krea 2', root: '/home/leo/models/d/diffusion_models' }],
    ]);

    await manager.selectFolder('D:/Krea 2');

    expect(manager.selectedPath).toBe('D:/Krea 2');
    expect(manager.pageControls.pageState.activeFolder).toBe('Krea 2');
    expect(manager.pageControls.pageState.activeFolderRoot).toBe('/home/leo/models/d/diffusion_models');
    expect(getStorageItem('checkpoints_activeFolderKey')).toBe('D:/Krea 2');
  });

  it('restores a drive root as a root-only filter', () => {
    localStorage.setItem('lora_manager_checkpoints_activeFolder', '');
    localStorage.setItem('lora_manager_checkpoints_activeFolderRoot', '/mnt/g/models/checkpoints');
    localStorage.setItem('lora_manager_checkpoints_activeFolderKey', 'G:');
    const manager = createManager('');

    manager.restoreSelectedFolder();

    expect(manager.selectedPath).toBe('G:');
    expect(manager.pageControls.pageState.activeFolder).toBe('');
    expect(manager.pageControls.pageState.activeFolderRoot).toBe('/mnt/g/models/checkpoints');
  });
  it('builds separate storage and category branches for duplicate folder names', () => {

    const manager = createManager('');
    manager.folderEntries = [
      {
        path: 'Krea 2',
        root: '/ai2/models/comfyui/diffusion_models',
        drive: 'AI2',
        storage: 'AI2',
        category: 'diffusion_models',
      },
      {
        path: 'Krea 2',
        root: '/ai3/models/comfyui/diffusion_models',
        drive: 'AI3',
        storage: 'AI3',
        category: 'diffusion_models',
      },
    ];

    manager.buildDriveAwareFolderData();

    expect(manager.treeData).toEqual({
      AI2: { diffusion_models: { 'Krea 2': {} } },
      AI3: { diffusion_models: { 'Krea 2': {} } },
    });
    expect(manager.folderSelectionMap.get('AI2/diffusion_models/Krea 2')).toEqual({
      path: 'Krea 2',
      root: '/ai2/models/comfyui/diffusion_models',
    });
    expect(manager.folderSelectionMap.get('AI3/diffusion_models/Krea 2')).toEqual({
      path: 'Krea 2',
      root: '/ai3/models/comfyui/diffusion_models',
    });
    expect(manager.folderSelectionMap.get('AI2').selectable).toBe(false);
  });

  it('migrates an old display key by matching the stored path and root', () => {
    localStorage.setItem('lora_manager_checkpoints_activeFolder', 'Illustrious');
    localStorage.setItem(
      'lora_manager_checkpoints_activeFolderRoot',
      '/ai3/models/comfyui/checkpoints',
    );
    localStorage.setItem(
      'lora_manager_checkpoints_activeFolderKey',
      'CHECKPOINTS:/Illustrious',
    );
    const manager = createManager('');
    manager.folderSelectionMap = new Map([
      [
        'AI3/checkpoints/Illustrious',
        { path: 'Illustrious', root: '/ai3/models/comfyui/checkpoints' },
      ],
    ]);

    manager.restoreSelectedFolder();

    expect(manager.selectedPath).toBe('AI3/checkpoints/Illustrious');
  });

  it('does not select a storage-only grouping node', async () => {
    const manager = createManager('');
    manager.folderSelectionMap = new Map([
      ['AI3', { path: null, root: null, selectable: false }],
    ]);

    await manager.selectFolder('AI3');

    expect(manager.pageControls.resetAndReload).not.toHaveBeenCalled();
    expect(manager.selectedPath).toBe('');
  });
});
