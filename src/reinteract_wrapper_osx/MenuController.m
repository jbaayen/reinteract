/* -*- mode: ObjC; c-basic-offset: 4; indent-tabs-mode: nil; -*-
 *
 * Copyright 2008 Owen Taylor
 *
 * This file is part of Reinteract and distributed under the terms
 * of the BSD license. See the file COPYING in the Reinteract
 * distribution for full details.
 *
 ************************************************************************/

#include <config.h>

#import "MenuController.h"

/* The MenuController object is a delegate that receives messages when
 * most of our menu items in the menu are selected. (A few of them are
 * wired directly to standard Cocoa functionality.)
 *
 * Each menu item has as its action a selector (method reference)
 * with the name corresponding to the action name used within our
 * PyGTK code. (newWorksheet for the 'new-worksheet' action, etc.)
 *
 * When we get a message, we convert the selector into the action name
 * and call into Python (by way of the actionCallback function.) We
 * also support enabling and disabling menu items by action name.
 */

@implementation MenuController

-(id)init
{
    actionToMenuItem = [[NSMutableDictionary alloc] init];

    return self;
}

-(void)setActionCallback:(MenuActionCallback)callback callbackData:(void *)callbackData
{
    actionCallback = callback;
    actionCallbackData = callbackData;
}

// Convert a selector name (newWorksheet:) to the action name
// (new-worksheet). The function here is the same as:
//
// result = re.sub('([A-Z])', lambda m: "-" + m.group(1).lower(), selector[:-1])
//
static NSString *
selectorToActionName(SEL selector)
{
    NSString *str = NSStringFromSelector(selector);
    NSMutableString *result = [NSMutableString stringWithCapacity:[str length]];

    int length = [str length] - 1; // Remove trailing :
    int i = 0;
    int last = 0;
    for (i = 0; i < length; i++) {
        unichar c = [str characterAtIndex:i];
        if (c >= 'A' && c <= 'Z') {
            [result appendString:[str substringWithRange:NSMakeRange(last, i - last)]];
            unichar c2[2];
            c2[0] = '-';
            c2[1] = c + ('a' - 'A');
            NSString *tmp = [NSString stringWithCharacters:c2 length:2];
            [result appendString:tmp];
            last = i + 1;
        }
    }
    [result appendString:[str substringWithRange:NSMakeRange(last, i - last)]];
    return result;
}

-(void)addActionsFromMenu:(NSMenu *)menu
{
    NSArray *items = [menu itemArray];
    int i;
    for (i = 0; i < [items count]; i++) {
        NSMenuItem *item = [items objectAtIndex:i];
        if ([item hasSubmenu])
            [self addActionsFromMenu:[item submenu]];
        else if ([item target] == self) {
            [actionToMenuItem setObject:item forKey:selectorToActionName([item action])];
        }
    }
}

-(void)activateAction:(id)sender
{
    if (actionCallback)
        actionCallback(selectorToActionName([sender action]), actionCallbackData);
}

// The delegate methods for individual menu items just call the generic
// activateAction method and we figure out what action was selected from
// the sender (that is, the menu item.)

-(void)about:(id)sender
{
    [self activateAction:sender];
}

-(void)break:(id)sender
{
    [self activateAction:sender];
}

-(void)calculate:(id)sender
{
    [self activateAction:sender];
}

-(void)calculateAll:(id)sender
{
    [self activateAction:sender];
}

-(void)close:(id)sender
{
    [self activateAction:sender];
}

-(void)cut:(id)sender
{
    [self activateAction:sender];
}

-(void)copy:(id)sender
{
    [self activateAction:sender];
}

-(void)copyAsDoctests:(id)sender
{
    [self activateAction:sender];
}

-(void)delete:(id)sender
{
    [self activateAction:sender];
}

-(void)newLibrary:(id)sender
{
    [self activateAction:sender];
}

-(void)newNotebook:(id)sender
{
    [self activateAction:sender];
}

-(void)newWorksheet:(id)sender
{
    [self activateAction:sender];
}

-(void)notebookProperties:(id)sender
{
    [self activateAction:sender];
}

-(void)openNotebook:(id)sender
{
    [self activateAction:sender];
}

-(void)open:(id)sender
{
    [self activateAction:sender];
}

-(void)paste:(id)sender
{
    [self activateAction:sender];
}

-(void)preferences:(id)sender
{
    [self activateAction:sender];
}

-(void)redo:(id)sender
{
    [self activateAction:sender];
}

-(void)rename:(id)sender
{
    [self activateAction:sender];
}

-(void)quit:(id)sender
{
    [self activateAction:sender];
}

-(void)save:(id)sender
{
    [self activateAction:sender];
}

-(void)undo:(id)sender
{
    [self activateAction:sender];
}

-(void)enableAction:(NSString *)actionName
{
    NSMenuItem *item = [actionToMenuItem objectForKey:actionName];
    [item setEnabled:YES];
}

-(void)disableAction:(NSString *)actionName
{
    NSMenuItem *item = [actionToMenuItem objectForKey:actionName];
    [item setEnabled:NO];
}

-(NSArray *)actionNames
{
    return [actionToMenuItem allKeys];
}

@end
