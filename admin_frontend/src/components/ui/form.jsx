import * as React from "react";
import { Controller } from "react-hook-form";

import { cn } from "@/lib/utils";

const Form = ({ className, ...props }) => <form className={cn(className)} {...props} />;
Form.displayName = "Form";

const FormField = ({ control, name, render }) => {
  return <Controller control={control} name={name} render={render} />;
};
FormField.displayName = "FormField";

const FormItem = React.forwardRef(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("space-y-2", className)} {...props} />
));
FormItem.displayName = "FormItem";

const FormLabel = React.forwardRef(({ className, ...props }, ref) => (
  <label ref={ref} className={cn("text-sm font-medium leading-none", className)} {...props} />
));
FormLabel.displayName = "FormLabel";

const FormControl = React.forwardRef(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("grid gap-2", className)} {...props} />
));
FormControl.displayName = "FormControl";

const FormDescription = React.forwardRef(({ className, ...props }, ref) => (
  <p ref={ref} className={cn("text-sm text-muted-foreground", className)} {...props} />
));
FormDescription.displayName = "FormDescription";

const FormMessage = React.forwardRef(({ className, children, ...props }, ref) => {
  return (
    <p ref={ref} className={cn("text-sm text-destructive", className)} {...props}>
      {children}
    </p>
  );
});
FormMessage.displayName = "FormMessage";

export { Form, FormItem, FormLabel, FormControl, FormDescription, FormMessage, FormField };
