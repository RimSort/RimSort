param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Inspect', 'Transform', 'State', 'Related')][string]$Mode,
    [string]$MsiPath,
    [string]$TransformPath,
    [string]$PythonPath,
    [string]$LaunchArguments,
    [string]$ProductCode,
    [string]$ComponentCode,
    [string]$UpgradeCode
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Invoke-ComMember($Object, [string]$Name, [string]$Operation, [object[]]$Arguments = @()) {
    $Object.GetType().InvokeMember($Name, $Operation, $null, $Object, $Arguments)
}

function Read-MsiRows($Database, [string]$Sql, [int]$Columns) {
    $view = Invoke-ComMember $Database 'OpenView' 'InvokeMethod' @($Sql)
    $rows = New-Object 'System.Collections.Generic.List[object]'
    try {
        [void](Invoke-ComMember $view 'Execute' 'InvokeMethod')
        while ($null -ne ($record = Invoke-ComMember $view 'Fetch' 'InvokeMethod')) {
            $values = @()
            for ($column = 1; $column -le $Columns; $column++) {
                $values += [string](Invoke-ComMember $record 'StringData' 'GetProperty' @($column))
            }
            $rows.Add($values)
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($record)
        }
    } finally {
        [void](Invoke-ComMember $view 'Close' 'InvokeMethod')
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    }
    return ,$rows.ToArray()
}

function Write-MsiRow($Installer, $Database, [string]$Sql, [string[]]$Values) {
    $record = Invoke-ComMember $Installer 'CreateRecord' 'InvokeMethod' @($Values.Count)
    $view = Invoke-ComMember $Database 'OpenView' 'InvokeMethod' @($Sql)
    try {
        for ($column = 1; $column -le $Values.Count; $column++) {
            [void](Invoke-ComMember $record 'StringData' 'SetProperty' @($column, $Values[$column - 1]))
        }
        [void](Invoke-ComMember $view 'Execute' 'InvokeMethod' @($record))
    } finally {
        [void](Invoke-ComMember $view 'Close' 'InvokeMethod')
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($record)
    }
}

$installer = New-Object -ComObject WindowsInstaller.Installer
$database = $null
$reference = $null
$workingCopy = $null
try {
    if ($Mode -eq 'Related') {
        $products = Invoke-ComMember $installer 'RelatedProducts' 'GetProperty' @($UpgradeCode)
        $result = @()
        if ($null -ne $products) {
            foreach ($product in $products) { $result += [string]$product }
        }
        ConvertTo-Json -InputObject $result -Compress
    } elseif ($Mode -eq 'State') {
        $state = Invoke-ComMember $installer 'ProductState' 'GetProperty' @($ProductCode)
        $location = ''
        if ($state -eq 5) {
            $location = Invoke-ComMember $installer 'ComponentPath' 'GetProperty' @($ProductCode, $ComponentCode)
        }
        @{ state = $state; executable = $location } | ConvertTo-Json -Compress
    } elseif ($Mode -eq 'Inspect') {
        $database = Invoke-ComMember $installer 'OpenDatabase' 'InvokeMethod' @($MsiPath, 0)
        $properties = @{}
        foreach ($row in (Read-MsiRows $database 'SELECT `Property`, `Value` FROM `Property`' 2)) {
            $properties[$row[0]] = $row[1]
        }
        @{
            properties = $properties
            directories = Read-MsiRows $database 'SELECT `Directory`, `Directory_Parent`, `DefaultDir` FROM `Directory`' 3
            components = Read-MsiRows $database 'SELECT `Component`, `ComponentId`, `Directory_` FROM `Component`' 3
            files = Read-MsiRows $database 'SELECT `FileName`, `Component_` FROM `File`' 2
        } | ConvertTo-Json -Depth 6 -Compress
    } else {
        $workingCopy = "$TransformPath.working.msi"
        Copy-Item -LiteralPath $MsiPath -Destination $workingCopy
        $reference = Invoke-ComMember $installer 'OpenDatabase' 'InvokeMethod' @($MsiPath, 0)
        $database = Invoke-ComMember $installer 'OpenDatabase' 'InvokeMethod' @($workingCopy, 1)
        $launch = Read-MsiRows $database "SELECT ``Source``, ``Target`` FROM ``CustomAction`` WHERE ``Action`` = 'LaunchRimSortAfterInstall'" 2
        $target = Read-MsiRows $database "SELECT ``Source``, ``Target`` FROM ``CustomAction`` WHERE ``Action`` = 'SetRimSortTarget'" 2
        if ($launch.Count -ne 1 -or $launch[0][0] -ne 'RIMSORTTARGET' -or $launch[0][1] -ne '' -or
            $target.Count -ne 1 -or $target[0][0] -ne 'RIMSORTTARGET' -or $target[0][1] -ne '[INSTALLFOLDER]RimSort.exe') {
            throw 'Unexpected production MSI launch actions; update the test boundary explicitly.'
        }
        Write-MsiRow $installer $database 'INSERT INTO `Property` (`Property`, `Value`) VALUES (?, ?)' @('RIMSORTTESTPYTHON', $PythonPath)
        Write-MsiRow $installer $database "UPDATE ``CustomAction`` SET ``Source`` = ?, ``Target`` = ? WHERE ``Action`` = 'LaunchRimSortAfterInstall'" @('RIMSORTTESTPYTHON', $LaunchArguments)
        [void](Invoke-ComMember $database 'Commit' 'InvokeMethod')
        $generated = Invoke-ComMember $database 'GenerateTransform' 'InvokeMethod' @($reference, $TransformPath)
        if (-not $generated) { throw 'MSI launch transform contains no changes.' }
        [void](Invoke-ComMember $database 'CreateTransformSummaryInfo' 'InvokeMethod' @($reference, $TransformPath, 0, 3))
    }
} finally {
    foreach ($item in @($database, $reference, $installer)) {
        if ($null -ne $item) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($item) }
    }
    if ($workingCopy -and (Test-Path -LiteralPath $workingCopy)) {
        Remove-Item -LiteralPath $workingCopy
    }
}
