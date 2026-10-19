"""Physical-axis linear/bilinear resampling, with no extrapolation or writes."""
import numpy as np
from .model import MapDefinition


def _axis(values,count,other_count):
    if count==1 and other_count==1 and not values:return np.array([0.])
    a=np.asarray(values,dtype=float)
    if a.shape!=(count,) or not np.isfinite(a).all():
        raise ValueError('Achsen fehlen oder sind nicht endlich')
    if count>1 and not (np.all(np.diff(a)>0) or np.all(np.diff(a)<0)):
        raise ValueError('Achsen müssen strikt monoton und ohne doppelte Stützstellen sein')
    return a


def resample_surface(values, source:MapDefinition, target:MapDefinition):
    """Keep physical axis order; reverse descending source axes with their data.

    Units must be explicitly equal. Unknown units and swapped axis channels are
    conflicts. A singleton needs a physical coordinate when the other grid varies.
    """
    a=np.asarray(values,dtype=float)
    if a.shape!=(source.rows,source.cols) or not np.isfinite(a).all():
        raise ValueError('Ungültige Quelloberfläche')
    if not source.unit.strip() or source.unit!=target.unit:
        raise ValueError('Unterschiedliche Werteinheiten')
    changed_grid=((source.rows,source.cols)!=(target.rows,target.cols) or
                  source.axes_x!=target.axes_x or source.axes_y!=target.axes_y)
    if (changed_grid and min(source.rows,source.cols,target.rows,target.cols)>1 and
            source.axis_x_unit==source.axis_y_unit and
            (not all((source.axis_x_channel,source.axis_y_channel,target.axis_x_channel,target.axis_y_channel)) or
             source.axis_x_channel==source.axis_y_channel)):
        raise ValueError('Achsenrollen bei gleichen Einheiten nicht eindeutig belegt')
    coords=[]
    for side,n,nt in [('x',source.cols,target.cols),('y',source.rows,target.rows)]:
        unit=getattr(source,'axis_'+side+'_unit').strip()
        other_unit=getattr(target,'axis_'+side+'_unit').strip()
        if max(n,nt)>1 and (not unit or unit.casefold() in ('unknown','unbekannt','raw','index','?') or unit!=other_unit):
            raise ValueError('Gleiche belegte physikalische Achseneinheiten erforderlich')
        channel=getattr(source,'axis_'+side+'_channel').strip().casefold()
        other_channel=getattr(target,'axis_'+side+'_channel').strip().casefold()
        if channel and other_channel and channel!=other_channel:
            raise ValueError('Unterschiedliche Achsenrollen: '+side.upper())
        x=_axis(getattr(source,'axes_'+side),n,nt)
        xt=_axis(getattr(target,'axes_'+side),nt,n)
        if np.any(xt<np.min(x)) or np.any(xt>np.max(x)):
            raise ValueError('Zielstützstellen außerhalb des Quellbereichs: keine Extrapolation')
        coords.append((x,xt))
    (x,xt),(y,yt)=coords
    if len(x)>1 and x[0]>x[-1]:x=x[::-1];a=a[:,::-1]
    if len(y)>1 and y[0]>y[-1]:y=y[::-1];a=a[::-1,:]
    along_x=np.array([np.interp(xt,x,row) for row in a])
    result=np.array([np.interp(yt,y,along_x[:,col]) for col in range(len(xt))]).T
    if not np.isfinite(result).all():raise ValueError('Nichtendliches Interpolationsergebnis')
    return result
