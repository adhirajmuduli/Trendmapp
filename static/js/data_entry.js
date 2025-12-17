// AG Grid globals
let gridOptions;

/**
 * Dynamically generates column definitions from pivoted data.
 * @param {Array<Object>} pivotedData - The data from the API.
 * @returns {Array<Object>} AG Grid column definitions.
 */
function generateColumnDefs(pivotedData) {
  // If no data, create a default structure for new entries
  if (!pivotedData || pivotedData.length === 0) {
    return [
      { field: 'latitude', headerName: 'Latitude', editable: true, pinned: 'left', width: 120 },
      { field: 'longitude', headerName: 'Longitude', editable: true, pinned: 'left', width: 120 },
      {
        headerName: 'New Parameter',
        editable: true,
        headerGroupComponentParams: {
          template: '<div class="ag-header-group-cell-label">' +
                    '  <div class="ag-header-group-text" style="cursor: pointer;"></div>' +
                    '</div>'
        },
        children: [
          { headerName: 'YYYY-MM-DD', field: 'New_Parameter_YYYY-MM-DD', editable: true, filter: 'agNumberColumnFilter' }
        ]
      }
    ];
  }

  const dataKeys = Object.keys(pivotedData[0]);
  const paramGroups = {};

  // First, group all date-based columns by their parameter name
  dataKeys.forEach(key => {
    if (key === 'latitude' || key === 'longitude' || key === 'station_id') return;

    const parts = key.split('_');
    const paramName = parts.slice(0, -1).join('_');
    const date = parts.slice(-1)[0];

    if (!paramGroups[paramName]) {
      paramGroups[paramName] = [];
    }

    paramGroups[paramName].push({ 
      headerName: date, 
      field: key, 
      editable: true, 
      filter: 'agNumberColumnFilter' 
    });
  });

  // Sort children by date for each group
  for (const param in paramGroups) {
    paramGroups[param].sort((a, b) => new Date(a.headerName) - new Date(b.headerName));
  }

  // Build the final column definitions array
  const dynamicCols = Object.keys(paramGroups).map(paramName => ({
    headerName: paramName,
    editable: true,
    headerGroupComponentParams: {
      template: '<div class="ag-header-group-cell-label">' +
                '  <div class="ag-header-group-text" style="cursor: pointer;"></div>' +
                '</div>'
    },
    children: paramGroups[paramName].map(child => ({
      ...child,
      editable: true
    })),
    marryChildren: true
  }));

  // Return static columns plus the new dynamic groups
  return [
    { field: 'latitude', headerName: 'Latitude', editable: true, pinned: 'left', width: 120 },
    { field: 'longitude', headerName: 'Longitude', editable: true, pinned: 'left', width: 120 },
    ...dynamicCols
  ];
}

/**
 * Load data and dynamically configure the grid.
 */
async function loadAndConfigureGrid() {
  try {
    showStatus('Loading data...', '#0078d4');
    const response = await fetch('/api/table');
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    
    const pivotedData = await response.json();
    console.log('Pivoted data loaded from API:', pivotedData);

    // Dynamically generate column definitions from the data
    const columnDefs = generateColumnDefs(pivotedData);
    gridOptions.api.setColumnDefs(columnDefs);

    let rowData = [];
    if (pivotedData.length > 0) {
      rowData = pivotedData;
      showStatus(`Loaded ${pivotedData.length} records.`, 'green');
    }
    // Preload 500 empty rows as workaround
    const emptyRowsToAdd = 500 - rowData.length;
    if (emptyRowsToAdd > 0) {
      for (let i = 0; i < emptyRowsToAdd; i++) rowData.push({});
    }
    gridOptions.api.setRowData(rowData);
    console.log('Row data length after preload:', rowData.length);
    console.log('Displayed rows:', gridOptions.api.getDisplayedRowCount());
    showStatus(`Grid ready with ${rowData.length} rows.`, 'green'); // Clear status message
  } catch (error) {
    console.error('Error loading or configuring grid:', error);
    showStatus('Error: ' + (error.message || 'Unknown error'), 'red');
  }
}

/**
 * Initializes the AG Grid with default options.
 */
function initializeGrid() {
  const gridDiv = document.getElementById('data-grid');
  if (!gridDiv) {
    showStatus('Error: Grid container not found.', 'red');
    return;
  }

  gridOptions = {
    defaultColDef: {
      resizable: true,
      sortable: true,
      filter: true,
    },
    columnDefs: [],
    rowData: [],
    suppressMovableColumns: true,
    enableRangeSelection: true,
    enableFillHandle: true,
    enableClipboard: true,
    clipboardDelimiter: '\t',
    onGridReady: (params) => {
      console.log('AG Grid is ready.');
      gridOptions.api = params.api; // Store the API
      loadAndConfigureGrid(); // Load data and configure columns
    },
    processCellForClipboard: (params) => {
        return params.value;
    },
    processCellFromClipboard: (params) => {
        return params.value;
    },
    processDataFromClipboard: (params) => {
        const data = params.data;
        const focusedCell = gridOptions.api.getFocusedCell();
        if (!focusedCell || !data || data.length === 0) {
            return null;
        }

        const startRowIndex = focusedCell.rowIndex;
        const startColId = focusedCell.column.getColId();

        const colDefs = gridOptions.api.getColumnDefs();
        const flatCols = [];

        colDefs.forEach(def => {
            if (def.children) {
                def.children.forEach(child => flatCols.push(child));
            } else {
                flatCols.push(def);
            }
        });

        const startColIndex = flatCols.findIndex(col => col.field === startColId);
        if (startColIndex < 0) return null;

        for (let r = 0; r < data.length; r++) {
            const gridRow = gridOptions.api.getDisplayedRowAtIndex(startRowIndex + r);
            if (!gridRow) continue;

            const updatedRow = { ...gridRow.data };
            for (let c = 0; c < data[r].length; c++) {
                const colDef = flatCols[startColIndex + c];
                if (colDef && colDef.field) {
                    updatedRow[colDef.field] = data[r][c];
                }
            }

            gridOptions.api.applyTransaction({ update: [updatedRow] });
        }

        return null;
    },
    onHeaderCellDoubleClicked: handleHeaderDoubleClick,
    getContextMenuItems: getContextMenuItems,
  };

  // Create the grid
  new agGrid.Grid(gridDiv, gridOptions);

}

/**
 * Un-pivots the grid data and saves it to the server.
 */
async function saveTableData() {
  showStatus('Saving...', '#0078d4');
  
  const rowData = [];
  gridOptions.api.forEachNode(node => rowData.push(node.data));

  const isRowEmpty = (row) => {
    if (!row) return true;
    // A row is considered empty if all its own properties are null, undefined, or empty strings.
    const keys = Object.keys(row);
    if (keys.length === 0) return true;
    return keys.every(key => row[key] === null || row[key] === undefined || String(row[key]).trim() === '');
  };

  const nonEmptyData = rowData.filter(row => !isRowEmpty(row));

  if (nonEmptyData.length === 0) {
    showStatus('No data to save. The grid is empty.', 'orange');
    return;
  }

  const columnDefs = gridOptions.api.getColumnDefs();
  const unpivotedData = [];

  nonEmptyData.forEach((row, index) => {
    const station_id = row.station_id || `station_${index}`;
    const latitude = row.latitude;
    const longitude = row.longitude;

    if (latitude == null || String(latitude).trim() === '' || longitude == null || String(longitude).trim() === '') {
      console.warn('Skipping row with missing lat/lon:', row);
      return; // Skip rows without coordinates
    }

    columnDefs.forEach(group => {
      if (group.children) { // It's a parameter group
        const parameter = group.headerName;
        group.children.forEach(child => {
          const timestamp = child.headerName;
          const value = row[child.field];

          if (value != null && String(value).trim() !== '') {
            unpivotedData.push({
              station_id,
              latitude,
              longitude,
              parameter,
              timestamp,
              value
            });
          }
        });
      }
    });
  });

  if (unpivotedData.length === 0) {
    showStatus('No valid data to save.', 'orange');
    return;
  }

  try {
    showStatus(`Saving ${unpivotedData.length} measurements...`, '#0078d4');
    const response = await fetch('/api/table', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(unpivotedData),
    });

    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || 'Failed to save data');
    }

    showStatus('Data saved successfully!', 'green');
    setTimeout(() => { window.location.href = '/'; }, 1500);

  } catch (error) {
    console.error('Error saving data:', error);
    showStatus(`Error: ${error.message}`, 'red');
  }
}

function showStatus(message, color = '#0078d4') {
  const statusEl = document.getElementById('status');
  if (statusEl) {
    statusEl.textContent = message;
    statusEl.style.color = color;
    // Make status message disappear after 5 seconds if not an error
    if (color !== 'red' && color !== 'orange') {
      setTimeout(() => {
        if (statusEl.textContent === message) {
          statusEl.textContent = '';
        }
      }, 5000);
    }
  }
}

/**
 * Shows a custom modal prompt.
 * @param {string} title - The title of the modal.
 * @param {string} text - The text content of the modal.
 * @param {string} defaultValue - The default value for the input field.
 * @returns {Promise<string|null>} A promise that resolves with the input value or null if cancelled.
 */
function showInputModal(title, text, defaultValue = '') {
    return new Promise((resolve) => {
        const modalElement = document.getElementById('inputModal');
        const modalTitle = document.getElementById('inputModalLabel');
        const modalText = document.getElementById('inputModalText');
        const modalInput = document.getElementById('inputModalField');
        const saveButton = document.getElementById('inputModalSave');
        const modal = bootstrap.Modal.getInstance(modalElement) || new bootstrap.Modal(modalElement);

        modalTitle.textContent = title;
        modalText.textContent = text;
        modalInput.value = defaultValue;

        // Remove any existing listeners to prevent duplicates
        const newSaveButton = saveButton.cloneNode(true);
        saveButton.parentNode.replaceChild(newSaveButton, saveButton);

        let onSave, onCancel;

        onSave = () => {
            // When saving, we must remove the cancel listener to prevent it from firing when we hide the modal.
            modalElement.removeEventListener('hidden.bs.modal', onCancel);
            resolve(modalInput.value);
            modal.hide();
        };

        onCancel = () => {
            // When cancelling, we must remove the save listener.
            newSaveButton.removeEventListener('click', onSave);
            resolve(null);
        };

        newSaveButton.addEventListener('click', onSave, { once: true });
        modalElement.addEventListener('hidden.bs.modal', onCancel, { once: true });

        modal.show();
    });
}

/**
 * Adds a new parameter group to the grid.
 */
async function addParameterColumn() {
  console.log('addParameterColumn clicked');
  const paramName = await showInputModal('New Parameter', 'Enter the name for the new parameter:', 'New Parameter');
  if (!paramName) return;

  const date = await showInputModal('New Timestamp', 'Enter the initial timestamp (YYYY-MM-DD):', new Date().toISOString().split('T')[0]);
  if (!date) return;

  const newField = `${paramName}_${date}`;
  const newColumn = {
    headerName: paramName,
    editable: true,
    marryChildren: true,
    headerGroupComponentParams: {
      template: '<div class="ag-header-group-cell-label">' +
                '  <div class="ag-header-group-text" style="cursor: pointer;"></div>' +
                '</div>'
    },
    children: [
      { headerName: date, field: newField, editable: true, filter: 'agNumberColumnFilter' }
    ]
  };

  const currentDefs = gridOptions.api.getColumnDefs();
  // keep first two static groups (Lat, Lon) then add new param groups afterwards
  const staticGroups = currentDefs.filter(d => d.headerName === 'Latitude' || d.headerName === 'Longitude');
  const otherGroups = currentDefs.filter(d => !(d.headerName === 'Latitude' || d.headerName === 'Longitude'));
  gridOptions.api.setColumnDefs([...staticGroups, ...otherGroups, newColumn]);
  gridOptions.api.refreshHeader();
  console.log('Parameter added', newColumn);
}

/**
 * Adds a new timestamp column to one or all existing parameter groups.
 */
async function addTimestampColumn() {
  console.log('addTimestampColumn clicked');
  const currentDefs = gridOptions.api.getColumnDefs();
  const parameters = currentDefs
    .filter(group => group.children && group.headerName && !['Latitude','Longitude'].includes(group.headerName))
    .map(group => group.headerName);

  if (parameters.length === 0) {
    showStatus('Please add a parameter before adding a timestamp.', 'orange');
    return;
  }

  const targetParam = await showInputModal('Select Parameter', `Enter the parameter to add the timestamp to, or type 'all' for every parameter.\nAvailable parameters: ${parameters.join(', ')}`, 'all');
  if (!targetParam) return; // User cancelled

  const date = await showInputModal('New Timestamp', 'Enter the new timestamp (YYYY-MM-DD):', new Date().toISOString().split('T')[0]);
  if (!date) return; // User cancelled

  const newDefs = currentDefs.map(group => {
    if (group.children && group.headerName) { // It's a parameter group
      const paramName = group.headerName;
      if (targetParam.toLowerCase() === 'all' || paramName === targetParam) {
        const newField = `${paramName}_${date}`;
        // Check if timestamp already exists for this parameter
        if (group.children.some(child => child.headerName === date)) {
          showStatus(`Timestamp ${date} already exists for parameter ${paramName}.`, 'orange');
          return group; // Return group unmodified
        }

        const newChild = { headerName: date, field: newField, editable: true, filter: 'agNumberColumnFilter' };
        const updatedChildren = [...group.children, newChild].sort((a, b) => new Date(a.headerName) - new Date(b.headerName));

        return {
          ...group,
          children: updatedChildren
        };
      }
    }
    return group; // Not a parameter group or not the target parameter
  });

  gridOptions.api.setColumnDefs(newDefs);
  gridOptions.api.refreshHeader();
  console.log('Timestamp added to', targetParam, date);
}

/**
 * Handles the logic for editing a header name on double-click.
 * @param {object} params - The AG Grid event parameters.
 */
async function handleHeaderDoubleClick(params) {
    const { column, columnGroup } = params;

    if (!column && !columnGroup) {
        console.warn('No column or group found on double-click event.');
        return;
    }

    const isGroup = !column && columnGroup;
    const colDef = isGroup ? columnGroup.getOriginalColumnGroup().getColGroupDef() : column.getColDef();
    const oldName = colDef.headerName;

    let newName;
    if (isGroup) {
        newName = await showInputModal('Edit Parameter Name', `Enter new parameter name for "${oldName}":`, oldName);
    } else {
        newName = await showInputModal('Edit Timestamp', `Enter new timestamp for "${oldName}" (YYYY-MM-DD):`, oldName);
    }

    if (!newName || newName.trim() === '' || newName.trim() === oldName) {
        return; // User cancelled or entered same name
    }
    newName = newName.trim();

    const currentDefs = gridOptions.api.getColumnDefs();
    const newDefs = JSON.parse(JSON.stringify(currentDefs));

    let updated = false;

    function findAndUpdate(defs) {
        for (let i = 0; i < defs.length; i++) {
            const def = defs[i];

            if (isGroup && def.children && def.headerName === oldName) {
                def.headerName = newName;
                def.children.forEach(child => {
                    child.field = `${newName}_${child.headerName}`;
                });
                updated = true;
                return;
            }

            if (!isGroup && def.field === column.getColId()) {
                const parentGroup = findParentGroup(newDefs, def.field);
                if (parentGroup) {
                    def.headerName = newName;
                    def.field = `${parentGroup.headerName}_${newName}`;
                    parentGroup.children.sort((a, b) => new Date(a.headerName) - new Date(b.headerName));
                    updated = true;
                }
                return;
            }

            if (def.children) {
                findAndUpdate(def.children);
                if (updated) return;
            }
        }
    }

    findAndUpdate(newDefs);

    if (updated) {
        gridOptions.api.setColumnDefs(newDefs);
        showStatus('Header updated successfully.', 'green');
    }
}

function findParentGroup(defs, field) {
    for (const group of defs) {
        if (group.children) {
            if (group.children.some(child => child.field === field)) {
                return group;
            }
        }
    }
    return null;
}

/**
 * Provides context menu items for grid headers.
 * @param {object} params - The AG Grid context menu parameters.
 * @returns {Array<object>} An array of menu items.
 */
function getContextMenuItems(params) {
  const { column, node } = params;
  if (!column) return [];

  const colDef = column.getColDef();
  const isGroup = column.getOriginalParent() !== null;

  let headerName = '';
  let deleteAction = null;

  if (isGroup) { // Right-clicked on a timestamp column
    headerName = colDef.headerName;
    deleteAction = () => deleteColumnOrGroup(colDef.field, true);
  } else if (column.isPrimary() && colDef.children) { // Right-clicked on a parameter group
    headerName = colDef.headerName;
    deleteAction = () => deleteColumnOrGroup(colDef.headerName, false);
  }

  if (deleteAction) {
    return [
      {
        name: `Delete '${headerName}'`,
        action: deleteAction,
        icon: '<span class="ag-icon ag-icon-cross" style="color: red;"></span>',
      },
      'separator',
      'autoSizeAll',
      'resetColumns',
    ];
  }

  return ['autoSizeAll', 'resetColumns'];
}

/**
 * Deletes a column or a whole parameter group from the grid.
 * @param {string} identifier - The field of the column or the headerName of the group.
 * @param {boolean} isChild - True if deleting a child (timestamp), false for a group (parameter).
 */
function deleteColumnOrGroup(identifier, isChild) {
  const currentDefs = gridOptions.api.getColumnDefs();
  let newDefs;

  if (isChild) {
    // Delete a single timestamp column
    newDefs = currentDefs.map(group => {
      if (group.children) {
        group.children = group.children.filter(child => child.field !== identifier);
      }
      return group;
    }).filter(group => !group.children || group.children.length > 0); // Remove group if it becomes empty
  } else {
    // Delete an entire parameter group
    newDefs = currentDefs.filter(group => group.headerName !== identifier);
  }

  gridOptions.api.setColumnDefs(newDefs);
  showStatus(`Deleted successfully.`, 'green');
}

/**
 * Sets up global event listeners for toolbar buttons.
 */
function setupEventListeners() {
  const btnAddParam = document.getElementById('btn-add-param');
  const btnAddTimestamp = document.getElementById('btn-add-timestamp');
  const btnSave = document.getElementById('btn-save');
  const btnCancel = document.getElementById('btn-cancel');

  if (btnAddParam) {
    btnAddParam.addEventListener('click', addParameterColumn);
  } else {
    console.error('Button with ID "btn-add-param" not found.');
  }

  if (btnAddTimestamp) {
    btnAddTimestamp.addEventListener('click', addTimestampColumn);
  } else {
    console.error('Button with ID "btn-add-timestamp" not found.');
  }

  if (btnSave) {
    btnSave.addEventListener('click', saveTableData);
  } else {
    console.error('Button with ID "btn-save" not found.');
  }

  if (btnCancel) {
    btnCancel.addEventListener('click', () => {
      if (confirm('Are you sure you want to cancel? Any unsaved changes will be lost.')) {
        window.location.href = '/';
      }
    });
  } else {
    console.error('Button with ID "btn-cancel" not found.');
  }
}

// Initialize immediately (script is at end of body so DOM is ready)
if (typeof agGrid === 'undefined') {
  showStatus('Error: AG Grid library failed to load.', 'red');
} else {
  initializeGrid();
  setupEventListeners();
}
